# page/MarkPricePage.py
import logging
from typing import List, Dict, Any
from nicegui import app, ui

# 导入UI卡片组件和类型提示
from modules.MarkPriceLive.MarkPriceLiveUI import create_instrument_management_card
from WsUtil.PublicSubscriptionManager import PublicSubscriptionManager
from WsUtil.PublicMessageDispatcher import PublicMessageDispatcher  # 添加类型提示
from modules.MarkPriceLive.MarkPriceProcessor import MarkPriceProcessor  # 添加类型提示

logger = logging.getLogger(__name__)


# ***** 修正函数签名以接收所有传入的参数 *****
def build_mark_price_page_layout(
        sub_mgr: PublicSubscriptionManager,
        dispatcher: PublicMessageDispatcher,  # 确保 dispatcher 被接收
        mark_price_proc: MarkPriceProcessor  # 确保 mark_price_proc 被接收
):
    # 构建标记价格监控页面的UI和交互逻辑。

    logger.info("构建标记价格页面UI...")

    # --- UI状态初始化 ---
    if 'watched_instruments_for_ui' not in app.storage.user:
        app.storage.user['watched_instruments_for_ui'] = sub_mgr.get_all_configured_instruments()

    # --- UI交互回调函数定义 ---
    async def _refresh_ui_and_sync_server_subscriptions():
        app.storage.user['watched_instruments_for_ui'] = sub_mgr.get_all_configured_instruments()
        active_desired_args = sub_mgr.get_enabled_subscription_args()
        await sub_mgr.sync_server_subscriptions(active_desired_args)
        instrument_cards_display_area.refresh()

    async def _add_instrument_handler(dialog: ui.dialog, input_field: ui.input):
        inst_id = input_field.value.strip().upper()
        if not inst_id: ui.notify("交易对ID不能为空", type='warning'); return

        channel = "mark-price"
        if sub_mgr.add_instrument_to_config(channel, inst_id, enabled=True):
            prefix = inst_id.lower().replace('-', '_')
            app.storage.user[f'{prefix}_mark_price'] = "---"
            app.storage.user[f'{prefix}_timestamp'] = "---"

            # 动态添加的交易对，也需要为其注册处理器
            # 注意：此处的 dispatcher 和 mark_price_proc 是从 build_mark_price_page_layout 的参数闭包捕获的
            dispatcher.register_handler(
                channel="mark-price",
                inst_id=inst_id,
                handler=mark_price_proc.process_message
            )

            await _refresh_ui_and_sync_server_subscriptions()
            ui.notify(f"已添加 {inst_id}", type='positive');
            dialog.close();
            input_field.set_value("")
        else:
            ui.notify(f"{inst_id} 已存在或添加失败", type='negative')

    async def _toggle_instrument_handler(inst_cfg: Dict[str, Any], new_status: bool):
        if sub_mgr.update_instrument_status_in_config(inst_cfg["channel"], inst_cfg["instId"], new_status):
            for item in app.storage.user['watched_instruments_for_ui']:
                if item["instId"] == inst_cfg["instId"] and item["channel"] == inst_cfg["channel"]:
                    item["enabled"] = new_status;
                    break
            app.storage.user['watched_instruments_for_ui'] = list(app.storage.user['watched_instruments_for_ui'])
            await _refresh_ui_and_sync_server_subscriptions()
            ui.notify(f"{inst_cfg['instId']} 已{'启用' if new_status else '禁用'}", type='info')

    async def _remove_instrument_handler(inst_cfg: Dict[str, Any]):
        with ui.dialog() as confirm_dialog, ui.card():
            ui.label(f"移除 {inst_cfg['instId']}?");
            ui.button('取消', on_click=confirm_dialog.close);
            ui.button('确定', color='negative', on_click=lambda: confirm_dialog.submit(True))

        if await confirm_dialog:
            if sub_mgr.remove_instrument_from_config(inst_cfg["channel"], inst_cfg["instId"]):
                prefix = inst_cfg['instId'].lower().replace('-', '_')
                for k_suffix in ['_mark_price', '_timestamp']:
                    if f'{prefix}{k_suffix}' in app.storage.user:
                        del app.storage.user[f'{prefix}{k_suffix}']

                # (可选) 从dispatcher注销此instId的特定处理器
                # dispatcher.unregister_handler(inst_cfg["channel"], inst_cfg["instId"], mark_price_proc.process_message)
                # 如果处理器注册是基于初始配置，并且动态添加时也注册了，那么移除时也应该注销。
                # 为保持简单，如果一个instId不再被任何配置项使用，其处理器可以保留，或者设计更复杂的处理器注销逻辑。

                await _refresh_ui_and_sync_server_subscriptions()
                ui.notify(f"已移除 {inst_cfg['instId']}", type='info')

    # --- 页面UI结构 ---
    ui.label("实时标记价格监控").classes("text-xl font-bold text-center my-3")
    with ui.dialog() as add_dialog, ui.card().classes('min-w-[300px]'):
        ui.label("添加新交易对").classes("text-lg font-semibold")
        new_id_input = ui.input(label="交易对ID (例如: BTC-USDT-SWAP)").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("取消", on_click=add_dialog.close, color='grey').props('outline')
            ui.button("添加", on_click=lambda: _add_instrument_handler(add_dialog,
                                                                       new_id_input))  # 回调现在能访问 sub_mgr, dispatcher, mark_price_proc

    ui.button("添加交易对", icon='add_circle_outline', on_click=add_dialog.open).classes("m-2 self-start")

    @ui.refreshable
    def instrument_cards_display_area():
        watched_instruments = app.storage.user.get('watched_instruments_for_ui', [])
        if not watched_instruments: ui.label("无监控交易对。").classes("m-2"); return
        with ui.row().classes('flex flex-wrap justify-start w-full'):
            for config_item in watched_instruments:
                create_instrument_management_card(
                    config_item,
                    on_toggle_enable=_toggle_instrument_handler,  # 回调现在能访问 sub_mgr
                    on_remove=_remove_instrument_handler  # 回调现在能访问 sub_mgr
                )

    instrument_cards_display_area()