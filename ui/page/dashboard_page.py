import asyncio
import logging
from nicegui import ui, app
from typing import cast  # 用于类型转换，配合NiceGUI的element

# 项目内部导入
from ws_util.public_channel_manager import PublicChannelManager
from ui.component.trading_pair_card import TradingPairCard  # TradingPairCard现在需要更多参数
import db_manager
from app_models import TradingPair

logger = logging.getLogger(__name__)

# 全局变量或使用 app.state 来管理核心服务实例
pcm_instance: PublicChannelManager | None = None
trading_pair_cards: dict[str, TradingPairCard] = {}
cards_container: ui.grid | None = None


def price_update_handler_factory(id_to_update: str):
    def handler(price: str):
        logger.debug(f"UI: 收到价格更新 for {id_to_update}: {price}")
        if id_to_update in trading_pair_cards:
            # 确保卡片仍然认为自己是启用的才更新价格文本
            if trading_pair_cards[id_to_update].is_enabled:
                trading_pair_cards[id_to_update].update_price(price)
        else:
            logger.warning(f"UI: 未找到 {id_to_update} 的卡片来更新价格。")

    return handler


async def handle_delete_pair(pair_id: int, inst_id: str, card_instance: TradingPairCard):
    """处理删除交易对的逻辑"""
    global pcm_instance
    logger.info(f"UI: 请求删除交易对 ID: {pair_id}, InstID: {inst_id}")

    confirm_dialog = ui.dialog()
    with confirm_dialog, ui.card():
        ui.label(f"确定要删除交易对 {inst_id} 吗？此操作不可恢复。")
        with ui.row().classes('justify-end w-full'):
            ui.button("取消", on_click=confirm_dialog.close)

            async def do_delete():
                confirm_dialog.close()
                # 1. 从数据库删除
                if db_manager.delete_trading_pair(pair_id):
                    logger.info(f"DB: 已删除交易对 ID: {pair_id}")

                    # 2. 取消订阅并注销回调
                    if pcm_instance:
                        await pcm_instance.unsubscribe_mark_price(inst_id)
                        pcm_instance.unregister_price_update_callback(inst_id)
                        logger.info(f"PCM: 已取消订阅并注销回调 for {inst_id}")

                    # 3. 从UI和内部字典中移除
                    if inst_id in trading_pair_cards:
                        del trading_pair_cards[inst_id]

                    # 从NiceGUI中删除卡片UI
                    # card_instance.ui_container.delete() # NiceGUI 0.9+
                    cast(ui.element, card_instance.ui_container).delete()  # 更通用的方式删除元素

                    ui.notify(f"已删除交易对 {inst_id}", type='positive', position='top')
                else:
                    logger.error(f"DB: 删除交易对 ID: {pair_id} 失败")
                    ui.notify(f"删除交易对 {inst_id} 失败", type='error', position='top')

            ui.button("删除", on_click=do_delete, color='negative')
    await confirm_dialog


async def handle_toggle_enable_pair(pair_id: int, inst_id: str, new_enabled_status: bool,
                                    card_instance: TradingPairCard):
    """处理启用/禁用交易对的逻辑"""
    global pcm_instance
    logger.info(f"UI: 请求切换交易对 ID: {pair_id}, InstID: {inst_id} 至状态: {new_enabled_status}")

    # 1. 更新数据库
    if db_manager.update_trading_pair(pair_id, {"is_enabled": new_enabled_status}):
        logger.info(f"DB: 已更新交易对 ID: {pair_id} 的启用状态为 {new_enabled_status}")

        # 更新卡片实例的内部状态和UI
        card_instance.update_enabled_status_ui(new_enabled_status)

        # 2. 处理订阅/取消订阅和回调
        if pcm_instance:
            if new_enabled_status:
                logger.info(f"PCM: 为 {inst_id} 启用监控 (订阅并注册回调)")
                await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)  # 强制尝试订阅
                pcm_instance.register_price_update_callback(
                    inst_id,
                    price_update_handler_factory(inst_id)
                )
            else:
                logger.info(f"PCM: 为 {inst_id} 禁用监控 (取消订阅并注销回调)")
                await pcm_instance.unsubscribe_mark_price(inst_id)
                pcm_instance.unregister_price_update_callback(inst_id)

        ui.notify(f"交易对 {inst_id} 已 {'启用' if new_enabled_status else '禁用'}", type='info', position='top')
    else:
        logger.error(f"DB: 更新交易对 ID: {pair_id} 状态失败")
        ui.notify(f"更新 {inst_id} 状态失败", type='error', position='top')
        # 如果数据库更新失败，回滚UI状态
        card_instance.update_enabled_status_ui(not new_enabled_status)


async def setup_page_content():
    global pcm_instance, cards_container, trading_pair_cards

    # 在页面重建时，如果希望保持简单，可以考虑清空 trading_pair_cards
    # 但当前我们假设 trading_pair_cards 在应用生命周期内（非重启）是持久的，
    # 并且此函数主要在初始构建或需要完全重绘时被调用。
    # 如果此函数被频繁调用且 trading_pair_cards 未清空，可能会导致重复的UI元素或逻辑问题。
    # 为了简化，我们假设 trading_pair_cards 在调用此函数前是相关页面实例的最新状态。
    # 或者，更健壮的方式是在函数开始时清理旧卡片（如果它们仅由此函数管理）。
    # current_instIds_in_ui = set(trading_pair_cards.keys()) # 获取当前UI中的instId
    # db_instIds = set() # 之后会从数据库获取

    monitored_pairs_from_db = db_manager.get_all_trading_pairs()
    # for pair_model in monitored_pairs_from_db:
    #     db_instIds.add(pair_model.instId)

    # # 清理UI上存在但数据库中已不存在的卡片 (例如，如果数据库在外部被修改)
    # for inst_id_to_remove in current_instIds_in_ui - db_instIds:
    #     if inst_id_to_remove in trading_pair_cards:
    #         cast(ui.element, trading_pair_cards[inst_id_to_remove].ui_container).delete()
    #         del trading_pair_cards[inst_id_to_remove]
    #         logger.info(f"UI: 清理了数据库中不再存在的卡片: {inst_id_to_remove}")

    with ui.column().classes('items-center w-full q-pa-md'):
        ui.label("加密货币行情监控").classes('text-3xl font-bold text-primary mb-6')
        cards_container = ui.grid(columns=3).classes('gap-4 w-full max-w-4xl')

        with cards_container:
            # 确保trading_pair_cards在开始时是空的，或者正确地管理已存在的卡片
            # 为简单起见，这里假设在页面加载时，我们总是从数据库重建卡片列表的UI部分
            # 但Python对象可以复用（如果instId已在trading_pair_cards中）

            # 先清除cards_container中的所有旧UI元素，以避免重复添加
            cards_container.clear()
            # 清除trading_pair_cards字典，因为我们将根据数据库重新创建所有卡片对象和UI
            # 注意：这简化了UI重建逻辑，但如果卡片有复杂内部状态不想丢失，则需更细致处理
            existing_keys = list(trading_pair_cards.keys())
            for k in existing_keys:  # 先取消所有旧回调和订阅
                if pcm_instance:
                    await pcm_instance.unsubscribe_mark_price(k)  # 尝试取消订阅
                    pcm_instance.unregister_price_update_callback(k)  # 注销回调
            trading_pair_cards.clear()

            for pair_model in monitored_pairs_from_db:
                # 无论 pair_model.is_enabled 如何，都创建卡片，卡片内部会处理显示状态
                card = TradingPairCard(
                    inst_id=pair_model.instId,
                    pair_id=pair_model.id,  # 确保 pair_model.id 是有效的数据库ID
                    is_enabled=pair_model.is_enabled,
                    on_toggle_enable=handle_toggle_enable_pair,
                    on_delete=handle_delete_pair,
                    initial_price="加载中..."  # 卡片内部会根据is_enabled调整
                )
                trading_pair_cards[pair_model.instId] = card
                logger.info(
                    f"UI: 为 {pair_model.instId} (id: {pair_model.id}) 创建/更新了卡片。Enabled: {pair_model.is_enabled}")

                if pair_model.is_enabled:
                    if pcm_instance:
                        logger.debug(f"UI: 初始加载, 请求订阅 {pair_model.instId}")
                        await pcm_instance.subscribe_mark_price(pair_model.instId, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(
                            pair_model.instId,
                            price_update_handler_factory(pair_model.instId)
                        )
                # else: 卡片内部的 __init__ 会处理禁用时的视觉效果

        with ui.row(wrap=False).classes('mt-8 items-center gap-x-2'):
            new_inst_id_input = ui.input(label="添加交易对 (例如 BTC-USDT-SWAP)",
                                         placeholder="ETH-USDT-SWAP") \
                .props('outlined dense clearable').classes('flex-grow')

            async def handle_add_pair():
                global cards_container, pcm_instance  # 确保访问的是最新的全局变量

                inst_id = new_inst_id_input.value
                if not inst_id:
                    ui.notify("InstId 不能为空!", type='warning', position='top')
                    return

                inst_id = inst_id.strip().upper()
                new_inst_id_input.value = ''

                if inst_id in trading_pair_cards:
                    ui.notify(f"{inst_id} 已在监控列表中。", type='info', position='top')
                    return

                new_pair_model_data = TradingPair(instId=inst_id, is_enabled=True)
                pair_db_id = db_manager.add_trading_pair(new_pair_model_data)

                if pair_db_id is not None:
                    logger.info(f"UI: {inst_id} 已成功添加到数据库 (ID: {pair_db_id})。")
                    if cards_container is not None:
                        with cards_container:  # 将新卡片添加到UI容器
                            card = TradingPairCard(
                                inst_id=inst_id,
                                pair_id=pair_db_id,
                                is_enabled=True,
                                on_toggle_enable=handle_toggle_enable_pair,
                                on_delete=handle_delete_pair,
                                initial_price="待订阅..."
                            )
                            trading_pair_cards[inst_id] = card
                    else:
                        logger.error("UI: cards_container 未初始化，无法添加新卡片到UI。")

                    if pcm_instance:
                        logger.debug(f"UI: 添加新交易对后，请求订阅 {inst_id}")
                        await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(
                            inst_id,
                            price_update_handler_factory(inst_id)
                        )
                    ui.notify(f"已添加并开始监控 {inst_id}。", type='positive', position='top')
                else:
                    logger.warning(f"UI: 添加 {inst_id} 到数据库失败。可能已存在。")
                    existing_pair_in_db = None
                    all_db_pairs = db_manager.get_all_trading_pairs()
                    for p_db in all_db_pairs:
                        if p_db.instId == inst_id:
                            existing_pair_in_db = p_db
                            break
                    if existing_pair_in_db:
                        ui.notify(f"{inst_id} 已存在于数据库中。", type='info', position='top')
                    else:
                        ui.notify(f"添加 {inst_id} 到数据库时发生未知错误。", type='error', position='top')

            ui.button("添加监控", on_click=handle_add_pair).props('color=primary icon=add')


async def on_app_startup():
    global pcm_instance
    logging.info("Dashboard: 应用启动中...")
    db_manager.initialize_database()

    all_pairs = db_manager.get_all_trading_pairs()
    if not all_pairs:
        default_pair = TradingPair(instId="BTC-USDT-SWAP", is_enabled=True)
        added_id = db_manager.add_trading_pair(default_pair)
        if added_id:
            logging.info(f"已添加默认交易对 {default_pair.instId} (ID: {added_id}) 到数据库。")
        else:
            if not db_manager.get_all_trading_pairs():
                logging.error(f"添加默认交易对 {default_pair.instId} 到数据库失败，且数据库仍为空。")
            else:
                logging.info(f"默认交易对 {default_pair.instId} 可能已被其他方式添加。")

    if pcm_instance is None:
        pcm_instance = PublicChannelManager()
    asyncio.create_task(pcm_instance.start())
    logging.info("Dashboard: PublicChannelManager 启动任务已创建。")


async def on_app_shutdown():
    global pcm_instance, trading_pair_cards
    logging.info("Dashboard: 应用关闭中...")
    if pcm_instance:
        # 在停止PCM之前，注销所有回调并尝试取消订阅
        inst_ids_to_cleanup = list(trading_pair_cards.keys())
        logger.info(f"关闭前清理PCM订阅和回调 for: {inst_ids_to_cleanup}")
        for inst_id in inst_ids_to_cleanup:
            await pcm_instance.unsubscribe_mark_price(inst_id)
            pcm_instance.unregister_price_update_callback(inst_id)

        # 短暂等待，确保取消订阅消息有机会发出
        # await asyncio.sleep(0.5) # 根据网络情况调整或移除

        await pcm_instance.stop()
        logging.info("Dashboard: PublicChannelManager 已停止。")

    trading_pair_cards.clear()
    logger.info("Dashboard: trading_pair_cards 已清空。")


def create_dashboard_page():
    app.on_startup(on_app_startup)
    app.on_shutdown(on_app_shutdown)

    @ui.page('/')
    async def dashboard_page_builder():
        # 此函数在每次客户端连接到此页面时调用，或在热重载时调用。
        # 我们希望每次都基于数据库的当前状态构建UI。
        await setup_page_content()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s (%(threadName)s): %(message)s',  # 更详细的日志格式
        datefmt='%H:%M:%S'
    )
    create_dashboard_page()
    ui.run(
        title="OKX行情监控仪表盘",
        reload=False,  # reload=True 在开发复杂状态管理时需谨慎
        port=8080
    )