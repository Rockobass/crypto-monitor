# ui/page/dashboard_page.py
import asyncio
import logging
from nicegui import ui, app
from typing import cast, List, Optional
from ws_util.public_channel_manager import PublicChannelManager
from ui.component.trading_pair_card import TradingPairCard
from ui.component.rule_editor_form import RuleEditorForm
import db_manager
from app_models import TradingPair, AlertRule
from alert_system.alert_processor import AlertProcessor

logger = logging.getLogger(__name__)

# --- 全局变量 ---
pcm_instance: PublicChannelManager | None = None
alert_processor_instance: AlertProcessor | None = None
trading_pair_cards: dict[str, TradingPairCard] = {}
cards_container: ui.grid | None = None


def price_update_handler_factory(pair_id: int, inst_id: str):
    """为指定instId创建价格更新回调处理函数。"""

    async def handler(price: str):
        if inst_id in trading_pair_cards and trading_pair_cards[inst_id].is_enabled:
            trading_pair_cards[inst_id].update_price(price)

        if alert_processor_instance and trading_pair_cards[inst_id].is_enabled:
            alert_processor_instance.process_price_data(pair_id, price)

    return handler


# --- 预警规则管理回调函数 ---
async def _handle_save_alert_rule(rule_data: AlertRule, card_inst_id_to_refresh: str):
    """处理保存 (添加或更新) 预警规则"""
    global alert_processor_instance
    saved_rule_id: int | None = None
    is_new_rule = not rule_data.id

    if not is_new_rule and rule_data.id is not None: # 更新现有规则
        # 从待更新数据中排除 ID, pair_id (通常不应更改), 和运行时状态
        # 新增 'is_threshold_breached' 到排除列表
        update_payload = rule_data.model_dump(exclude={'id', 'pair_id', 'last_triggered_timestamp', 'is_threshold_breached'})
        success = db_manager.update_alert_rule(rule_data.id, update_payload)
        if success:
            saved_rule_id = rule_data.id
            ui.notify(f"规则 '{rule_data.name}' 已更新。", type='positive')
        else:
            ui.notify(f"更新规则 '{rule_data.name}' 失败。", type='error')
            return
    elif is_new_rule: # 添加新规则
        # add_alert_rule 在 db_manager 中显式指定列，不会尝试插入 is_threshold_breached
        new_rule_id = db_manager.add_alert_rule(rule_data)
        if new_rule_id:
            saved_rule_id = new_rule_id
            rule_data.id = new_rule_id
            ui.notify(f"规则 '{rule_data.name}' 已添加。", type='positive')
        else:
            ui.notify(f"添加规则 '{rule_data.name}' 失败。", type='error')
            return
    else:
        logger.error(f"保存规则时遇到意外情况: {rule_data}")
        return

    if saved_rule_id and alert_processor_instance:
        refreshed_rule = db_manager.get_alert_rule_by_id(saved_rule_id)
        if refreshed_rule:
            alert_processor_instance.update_rule_in_cache(refreshed_rule)
            await _refresh_card_rules(card_inst_id_to_refresh)
        else:
            logger.error(f"保存规则后未能从数据库取回规则ID: {saved_rule_id}")


async def _open_rule_editor(pair_id: int, inst_id: str, rule_to_edit: Optional[AlertRule] = None):
    """打开规则编辑器对话框"""
    async def save_wrapper(rule: AlertRule):
        await _handle_save_alert_rule(rule, inst_id)

    editor = RuleEditorForm(
        trading_pair_id=pair_id,
        inst_id=inst_id,
        on_save=save_wrapper,
        rule_to_edit=rule_to_edit
    )
    editor.open()


async def _handle_delete_alert_rule(rule_id: int, pair_id: int, card_inst_id_to_refresh: str):
    """处理删除预警规则"""
    global alert_processor_instance
    confirm_dialog = ui.dialog()
    rule_to_delete = db_manager.get_alert_rule_by_id(rule_id)
    rule_name = rule_to_delete.name if rule_to_delete else f"ID {rule_id}"

    with confirm_dialog, ui.card():
        ui.label(f"确定删除预警规则 '{rule_name}' 吗？")
        with ui.row().classes('justify-end w-full mt-4'):
            ui.button("取消", on_click=confirm_dialog.close, color='grey').props('flat')

            async def do_delete():
                confirm_dialog.close()
                if db_manager.delete_alert_rule(rule_id):
                    ui.notify(f"规则 '{rule_name}' 已删除。", type='positive')
                    if alert_processor_instance:
                        pair_info = db_manager.get_trading_pair_by_id(pair_id)
                        if pair_info:
                            alert_processor_instance.load_rules_for_pair(pair_id, pair_info.instId)
                    await _refresh_card_rules(card_inst_id_to_refresh)
                else:
                    ui.notify(f"删除规则 '{rule_name}' 失败。", type='error')

            ui.button("删除", on_click=do_delete, color='negative')
    await confirm_dialog


async def _handle_toggle_alert_rule_enabled(rule_id: int, new_status: bool, pair_id: int, card_inst_id_to_refresh: str):
    """处理切换预警规则的启用状态"""
    global alert_processor_instance
    if db_manager.update_alert_rule(rule_id, {"is_enabled": new_status}): # is_enabled 是表中的字段
        action_text = "启用" if new_status else "禁用"
        ui.notify(f"规则已{action_text}。", type='info')
        updated_rule = db_manager.get_alert_rule_by_id(rule_id)
        if updated_rule and alert_processor_instance:
            alert_processor_instance.update_rule_in_cache(updated_rule)
        await _refresh_card_rules(card_inst_id_to_refresh)
    else:
        ui.notify("更新规则状态失败。", type='error')
        await _refresh_card_rules(card_inst_id_to_refresh)


async def _refresh_card_rules(inst_id: str):
    """刷新指定交易对卡片上的预警规则列表"""
    if inst_id in trading_pair_cards:
        card = trading_pair_cards[inst_id]
        rules_for_card = db_manager.get_alert_rules_for_pair(card.pair_id)
        card.update_alert_rules_display(rules_for_card)
        logger.debug(f"已刷新卡片 {inst_id} 的预警规则显示。")


# --- 交易对核心操作 ---
async def _update_single_pair_monitoring_status(
        pair_id: int, inst_id: str, card: TradingPairCard, target_status: bool
) -> bool:
    global pcm_instance, alert_processor_instance
    if card.is_enabled == target_status:
        return True

    if not db_manager.update_trading_pair(pair_id, {"is_enabled": target_status}):
        logger.error(f"DB更新失败: {inst_id} 至 {target_status}")
        return False

    card.update_enabled_status_ui(target_status)
    logger.info(f"DB与UI更新: {inst_id} 至 {'启用' if target_status else '禁用'}")

    if target_status:
        if pcm_instance:
            logger.debug(f"PCM: 订阅 {inst_id}")
            await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
            pcm_instance.register_price_update_callback(inst_id, price_update_handler_factory(pair_id, inst_id))
        if alert_processor_instance:
            logger.debug(f"AlertProcessor: 加载规则 for {inst_id} (PairID: {pair_id})")
            alert_processor_instance.load_rules_for_pair(pair_id, inst_id)
    else:
        if pcm_instance:
            logger.debug(f"PCM: 取消订阅 {inst_id}")
            await pcm_instance.unsubscribe_mark_price(inst_id)
            pcm_instance.unregister_price_update_callback(inst_id)
        if alert_processor_instance:
            logger.debug(f"AlertProcessor: 移除规则 for {inst_id} (PairID: {pair_id})")
            alert_processor_instance.remove_rules_for_pair(pair_id)
    return True


async def handle_delete_pair(pair_id: int, inst_id: str, card: TradingPairCard):
    """处理删除交易对。"""
    global pcm_instance, alert_processor_instance
    confirm_dialog = ui.dialog()
    with confirm_dialog, ui.card():
        ui.label(f"确定删除 {inst_id} ？（其下所有预警规则也将被删除）")
        with ui.row().classes('justify-end w-full'):
            ui.button("取消", on_click=confirm_dialog.close)

            async def do_delete():
                confirm_dialog.close()
                was_enabled = card.is_enabled
                if db_manager.delete_trading_pair(pair_id):
                    if was_enabled:
                        if pcm_instance:
                            await pcm_instance.unsubscribe_mark_price(inst_id)
                            pcm_instance.unregister_price_update_callback(inst_id)
                        if alert_processor_instance:
                            alert_processor_instance.remove_rules_for_pair(pair_id)
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
        card.update_enabled_status_ui(not new_status)


async def mass_toggle_monitoring(enable_all: bool):
    """批量启用或禁用所有与目标状态不同的交易对。"""
    action_text = "启用" if enable_all else "禁用"
    to_process = [c for c in trading_pair_cards.values() if c.is_enabled != enable_all]
    if not to_process:
        ui.notify(f"所有交易对均已是“{action_text}”状态。", type='info')
        return

    results = await asyncio.gather(
        *(_update_single_pair_monitoring_status(c.pair_id, c.inst_id, c, enable_all) for c in to_process),
        return_exceptions=True
    )
    successful_ops = sum(1 for r in results if r is True)
    failed_ops = len(results) - successful_ops
    if successful_ops > 0: ui.notify(f"成功{action_text} {successful_ops} 个交易对。", type='positive')
    if failed_ops > 0: ui.notify(f"{failed_ops} 个交易对状态更新失败。", type='error')


async def setup_page_content():
    """构建或重建页面UI内容。"""
    global pcm_instance, cards_container, trading_pair_cards, alert_processor_instance

    with ui.column().classes('items-center w-full q-pa-md'):
        ui.label("加密货币行情监控").classes('text-3xl font-bold text-primary mb-6')

        with ui.row().classes('mb-4 gap-x-2'):
            ui.button("全部开始", on_click=lambda: mass_toggle_monitoring(True), icon='play_arrow', color='positive')
            ui.button("全部暂停", on_click=lambda: mass_toggle_monitoring(False), icon='pause', color='warning')

        current_cards_container = cards_container
        if current_cards_container:
            current_cards_container.clear()
        else:
            cards_container = ui.grid(columns=3).classes('gap-4 w-full max-w-5xl')
            current_cards_container = cards_container

        if pcm_instance:
            for inst_id_old in list(trading_pair_cards.keys()):
                await pcm_instance.unsubscribe_mark_price(inst_id_old)
                pcm_instance.unregister_price_update_callback(inst_id_old)
        if alert_processor_instance:
            # 从 AlertProcessor 的内部状态 _instId_map 获取 pair_id 列表进行清理
            # 注意：这里假设 _instId_map 的键是 pair_id
            for pair_id_old in list(alert_processor_instance._instId_map.keys()):
                alert_processor_instance.remove_rules_for_pair(pair_id_old)


        trading_pair_cards.clear()
        db_pairs = db_manager.get_all_trading_pairs()
        logger.info(f"从数据库加载到 {len(db_pairs)} 个交易对用于显示。")

        with current_cards_container:
            for pair_model in db_pairs:
                if not pair_model.id: continue

                rules_for_pair = db_manager.get_alert_rules_for_pair(pair_model.id)

                card = TradingPairCard(
                    inst_id=pair_model.instId, pair_id=pair_model.id, is_enabled=pair_model.is_enabled,
                    on_toggle_enable=handle_toggle_enable_pair,
                    on_delete=handle_delete_pair,
                    on_add_rule=lambda p_id=pair_model.id, i_id=pair_model.instId: _open_rule_editor(p_id, i_id),
                    on_edit_rule=lambda rule_model, i_id=pair_model.instId: _open_rule_editor(rule_model.pair_id, i_id, rule_model),
                    on_delete_rule=lambda r_id, p_id, i_id=pair_model.instId: _handle_delete_alert_rule(r_id, p_id, i_id),
                    on_toggle_rule_enabled=lambda r_id, status, p_id, i_id=pair_model.instId: _handle_toggle_alert_rule_enabled(r_id, status, p_id, i_id),
                    initial_rules=rules_for_pair
                )
                trading_pair_cards[pair_model.instId] = card

                if pair_model.is_enabled:
                    if pcm_instance:
                        await pcm_instance.subscribe_mark_price(pair_model.instId, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(
                            pair_model.instId, price_update_handler_factory(pair_model.id, pair_model.instId)
                        )
                    if alert_processor_instance:
                        alert_processor_instance.load_rules_for_pair(pair_model.id, pair_model.instId)

        with ui.row(wrap=False).classes('mt-8 items-center gap-x-2'):
            new_inst_id_input = ui.input(label="添加交易对 (例如 BTC-USDT-SWAP)", placeholder="ETH-USDT-SWAP") \
                .props('outlined dense clearable').classes('flex-grow')

            async def handle_add_pair_action():
                inst_id = new_inst_id_input.value.strip().upper()
                new_inst_id_input.value = ''
                if not inst_id: return ui.notify("InstId不能为空!", type='warning')
                if inst_id in trading_pair_cards: return ui.notify(f"{inst_id}已在监控中。", type='info')

                pair_db_id = db_manager.add_trading_pair(TradingPair(instId=inst_id, is_enabled=True))
                if pair_db_id and current_cards_container:
                    rules_for_new_pair = db_manager.get_alert_rules_for_pair(pair_db_id)
                    with current_cards_container:
                        card = TradingPairCard(
                            inst_id=inst_id, pair_id=pair_db_id, is_enabled=True,
                            on_toggle_enable=handle_toggle_enable_pair, on_delete=handle_delete_pair,
                            on_add_rule=lambda p_id=pair_db_id, i_id=inst_id: _open_rule_editor(p_id, i_id),
                            on_edit_rule=lambda rule_model, i_id=inst_id: _open_rule_editor(rule_model.pair_id, i_id, rule_model),
                            on_delete_rule=lambda r_id, p_id, i_id=inst_id: _handle_delete_alert_rule(r_id, p_id, i_id),
                            on_toggle_rule_enabled=lambda r_id, status, p_id, i_id=inst_id: _handle_toggle_alert_rule_enabled(r_id, status, p_id, i_id),
                            initial_rules=rules_for_new_pair,
                            initial_price="待订阅..."
                        )
                    trading_pair_cards[inst_id] = card
                    if pcm_instance:
                        await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(
                            inst_id, price_update_handler_factory(pair_db_id, inst_id)
                        )
                    if alert_processor_instance:
                        alert_processor_instance.load_rules_for_pair(pair_db_id, inst_id)
                    ui.notify(f"已添加并监控 {inst_id}", type='positive')
                elif not pair_db_id:
                    ui.notify(f"添加 {inst_id} 失败 (可能已在数据库中)", type='error')

            ui.button("添加监控", on_click=handle_add_pair_action).props('color=primary icon=add')


async def on_app_startup():
    global pcm_instance, alert_processor_instance
    logger.info("应用启动...")
    db_manager.initialize_database()
    if not db_manager.get_all_trading_pairs(): #
        db_manager.add_trading_pair(TradingPair(instId="BTC-USDT-SWAP", is_enabled=True)) #
        logger.info("已添加默认交易对 BTC-USDT-SWAP。") #

    if pcm_instance is None: pcm_instance = PublicChannelManager()
    if alert_processor_instance is None: alert_processor_instance = AlertProcessor()
    asyncio.create_task(pcm_instance.start())


async def on_app_shutdown():
    global pcm_instance, alert_processor_instance
    logger.info("应用关闭...")
    if pcm_instance:
        for inst_id in list(trading_pair_cards.keys()):
            card = trading_pair_cards.get(inst_id)
            if card and card.pair_id and alert_processor_instance:
                alert_processor_instance.remove_rules_for_pair(card.pair_id)
            await pcm_instance.unsubscribe_mark_price(inst_id)
            pcm_instance.unregister_price_update_callback(inst_id)
        await pcm_instance.stop()
    trading_pair_cards.clear()


def create_dashboard_page():
    app.on_startup(on_app_startup)
    app.on_shutdown(on_app_shutdown)

    @ui.page('/')
    async def dashboard_builder():
        await setup_page_content()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s [%(name)s:%(lineno)d] %(message)s',
                        datefmt='%H:%M:%S')
    create_dashboard_page()
    ui.run(title="OKX行情监控", reload=False, port=8080)