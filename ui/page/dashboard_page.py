import asyncio
import logging
from nicegui import ui, app
from typing import cast
from ws_util.public_channel_manager import PublicChannelManager
from ui.component.trading_pair_card import TradingPairCard  # 假设 TradingPairCard 保持不变
import db_manager
from app_models import TradingPair

logger = logging.getLogger(__name__)

# 全局变量
pcm_instance: PublicChannelManager | None = None
trading_pair_cards: dict[str, TradingPairCard] = {}
cards_container: ui.grid | None = None  # UI容器的引用


def price_update_handler_factory(inst_id: str):
    """为指定instId创建价格更新回调处理函数。"""

    def handler(price: str):
        if inst_id in trading_pair_cards and trading_pair_cards[inst_id].is_enabled:
            trading_pair_cards[inst_id].update_price(price)

    return handler


async def _update_single_pair_monitoring_status(
        pair_id: int, inst_id: str, card: TradingPairCard, target_status: bool
) -> bool:
    """核心：更新单个交易对的监控状态 (DB, UI, PCM)。返回DB操作是否成功。"""
    if card.is_enabled == target_status:  # 如果状态未变，则不执行操作
        return True  # 认为操作“成功”，因为状态已是目标状态

    if not db_manager.update_trading_pair(pair_id, {"is_enabled": target_status}):
        logger.error(f"DB更新失败: {inst_id} 至 {target_status}")
        return False

    card.update_enabled_status_ui(target_status)  # 更新卡片UI（包括is_enabled属性）
    logger.info(f"DB与UI更新: {inst_id} 至 {'启用' if target_status else '禁用'}")

    if pcm_instance:
        if target_status:  # 目标：启用
            logger.debug(f"PCM: 订阅 {inst_id}")
            await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
            pcm_instance.register_price_update_callback(inst_id, price_update_handler_factory(inst_id))
        else:  # 目标：禁用
            logger.debug(f"PCM: 取消订阅 {inst_id}")
            await pcm_instance.unsubscribe_mark_price(inst_id)
            pcm_instance.unregister_price_update_callback(inst_id)
    return True


async def handle_delete_pair(pair_id: int, inst_id: str, card: TradingPairCard):
    """处理删除交易对。"""
    confirm_dialog = ui.dialog()
    with confirm_dialog, ui.card():
        ui.label(f"确定删除 {inst_id} ？")
        with ui.row().classes('justify-end w-full'):
            ui.button("取消", on_click=confirm_dialog.close)

            async def do_delete():
                confirm_dialog.close()
                was_enabled = card.is_enabled  # 记录删除前的状态
                if db_manager.delete_trading_pair(pair_id):
                    if was_enabled and pcm_instance:  # 如果之前是启用的，才需要取消订阅
                        await pcm_instance.unsubscribe_mark_price(inst_id)
                        pcm_instance.unregister_price_update_callback(inst_id)
                    if inst_id in trading_pair_cards: del trading_pair_cards[inst_id]
                    cast(ui.element, card.ui_container).delete()
                    ui.notify(f"已删除 {inst_id}", type='positive')
                else:
                    ui.notify(f"删除 {inst_id} 失败", type='error')

            ui.button("删除", on_click=do_delete, color='negative')
    await confirm_dialog


async def handle_toggle_enable_pair(pair_id: int, inst_id: str, new_status: bool, card: TradingPairCard):
    """处理单个交易对启用/禁用切换。"""
    success = await _update_single_pair_monitoring_status(pair_id, inst_id, card, new_status)
    if success:
        ui.notify(f"{inst_id} 已{'启用' if new_status else '禁用'}", type='info')
    else:
        ui.notify(f"更新 {inst_id} 状态失败", type='error')
        card.update_enabled_status_ui(not new_status)  # DB失败时回滚UI


async def mass_toggle_monitoring(enable_all: bool):
    """批量启用或禁用所有与目标状态不同的交易对。"""
    action_text = "启用" if enable_all else "禁用"
    to_process = [c for c in trading_pair_cards.values() if c.is_enabled != enable_all]
    if not to_process:
        ui.notify(f"所有交易对均已是“{action_text}”状态。", type='info')
        return

    results = await asyncio.gather(
        *(_update_single_pair_monitoring_status(c.pair_id, c.inst_id, c, enable_all) for c in to_process),
        return_exceptions=True  # 收集所有结果，包括异常
    )

    successful_ops = sum(1 for r in results if r is True)
    failed_ops = len(results) - successful_ops

    if successful_ops > 0:
        ui.notify(f"成功{action_text} {successful_ops} 个交易对。", type='positive')
    if failed_ops > 0:
        ui.notify(f"{failed_ops} 个交易对状态更新失败。", type='error')
        # 对于失败的操作，其卡片UI可能没有被回滚（因为gather中单个失败不会触发单个的回滚逻辑）
        # 需要更复杂的逻辑来精确回滚批量操作中的失败项，或提示用户刷新
        logger.warning(f"批量{action_text}操作中，有{failed_ops}个失败，结果: {results}")
        # ui.notify("部分操作失败，建议刷新页面以同步状态。", type='warning', duration=7)


async def setup_page_content():
    """构建或重建页面UI内容。"""
    global pcm_instance, cards_container, trading_pair_cards

    with ui.column().classes('items-center w-full q-pa-md'):
        ui.label("加密货币行情监控").classes('text-3xl font-bold text-primary mb-6')

        with ui.row().classes('mb-4 gap-x-2'):
            ui.button("全部开始", on_click=lambda: mass_toggle_monitoring(True), icon='play_arrow', color='positive')
            ui.button("全部暂停", on_click=lambda: mass_toggle_monitoring(False), icon='pause', color='warning')

        current_cards_container = cards_container  # 捕获当前容器引用
        if current_cards_container:  # 如果容器已存在，先清空
            current_cards_container.clear()
        else:  # 如果容器不存在（首次加载），创建它
            cards_container = ui.grid(columns=3).classes('gap-4 w-full max-w-4xl')
            current_cards_container = cards_container

        # 清理PCM相关的旧资源 (订阅和回调)
        if pcm_instance:
            for inst_id_old in list(trading_pair_cards.keys()):  # 使用副本迭代
                await pcm_instance.unsubscribe_mark_price(inst_id_old)
                pcm_instance.unregister_price_update_callback(inst_id_old)
        trading_pair_cards.clear()  # 清空内存中的卡片字典

        db_pairs = db_manager.get_all_trading_pairs()
        logger.info(f"从数据库加载到 {len(db_pairs)} 个交易对用于显示。")

        with current_cards_container:  # 在（可能已清空的）容器内构建
            for pair_model in db_pairs:
                if not pair_model.id: continue  # 跳过无ID的记录 (不应发生)
                card = TradingPairCard(
                    inst_id=pair_model.instId, pair_id=pair_model.id, is_enabled=pair_model.is_enabled,
                    on_toggle_enable=handle_toggle_enable_pair, on_delete=handle_delete_pair
                )
                trading_pair_cards[pair_model.instId] = card
                if pair_model.is_enabled and pcm_instance:  # 如果启用，则订阅
                    await pcm_instance.subscribe_mark_price(pair_model.instId, resubscribe_check=False)
                    pcm_instance.register_price_update_callback(
                        pair_model.instId, price_update_handler_factory(pair_model.instId)
                    )

        # 添加新交易对的UI
        with ui.row(wrap=False).classes('mt-8 items-center gap-x-2'):
            new_inst_id_input = ui.input(label="添加交易对 (例如 BTC-USDT-SWAP)", placeholder="ETH-USDT-SWAP") \
                .props('outlined dense clearable').classes('flex-grow')

            async def handle_add_pair_action():
                inst_id = new_inst_id_input.value.strip().upper()
                new_inst_id_input.value = ''
                if not inst_id: return ui.notify("InstId不能为空!", type='warning')
                if inst_id in trading_pair_cards: return ui.notify(f"{inst_id}已在监控中。", type='info')

                pair_db_id = db_manager.add_trading_pair(TradingPair(instId=inst_id, is_enabled=True))
                if pair_db_id and current_cards_container:  # 确保ID有效且容器存在
                    with current_cards_container:  # 在现有容器中添加新卡片
                        card = TradingPairCard(
                            inst_id=inst_id, pair_id=pair_db_id, is_enabled=True,
                            on_toggle_enable=handle_toggle_enable_pair, on_delete=handle_delete_pair,
                            initial_price="待订阅..."
                        )
                    trading_pair_cards[inst_id] = card
                    if pcm_instance:  # 订阅新添加的
                        await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(inst_id, price_update_handler_factory(inst_id))
                    ui.notify(f"已添加并监控 {inst_id}", type='positive')
                elif not pair_db_id:  # 添加到DB失败
                    ui.notify(f"添加 {inst_id} 失败 (可能已在数据库中)", type='error')

            ui.button("添加监控", on_click=handle_add_pair_action).props('color=primary icon=add')


async def on_app_startup():
    global pcm_instance
    logger.info("应用启动...")
    db_manager.initialize_database()
    if not db_manager.get_all_trading_pairs():  # 如果数据库为空
        db_manager.add_trading_pair(TradingPair(instId="BTC-USDT-SWAP", is_enabled=True))
        logger.info("已添加默认交易对 BTC-USDT-SWAP。")

    if pcm_instance is None: pcm_instance = PublicChannelManager()
    asyncio.create_task(pcm_instance.start())  # 启动PCM


async def on_app_shutdown():
    global pcm_instance
    logger.info("应用关闭...")
    if pcm_instance:
        # 尝试清理所有已知订阅 (从trading_pair_cards获取，因PCM内部可能没有完整列表)
        for inst_id in list(trading_pair_cards.keys()):
            await pcm_instance.unsubscribe_mark_price(inst_id)
            pcm_instance.unregister_price_update_callback(inst_id)
        await pcm_instance.stop()
    trading_pair_cards.clear()


def create_dashboard_page():
    app.on_startup(on_app_startup)
    app.on_shutdown(on_app_shutdown)

    @ui.page('/')
    async def dashboard_builder(): await setup_page_content()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                        datefmt='%H:%M:%S')
    create_dashboard_page()
    ui.run(title="OKX行情监控", reload=False, port=8080)