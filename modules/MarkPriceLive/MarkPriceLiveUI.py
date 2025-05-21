# modules/MarkPriceLive/MarkPriceLiveUi.py
from nicegui import app, ui
import pandas as pd  # 假设用于时间戳格式化
from typing import Callable, Coroutine, Any, Dict  # 确保导入


def _format_timestamp_for_display(raw_ts_str: str) -> str:
    # 内部辅助函数：格式化时间戳。
    if not raw_ts_str or raw_ts_str == "---": return "---"
    try:
        # OKX时间戳是毫秒级字符串
        return pd.Timestamp(int(raw_ts_str), unit='ms', tz='UTC').strftime('%H:%M:%S.%f')[:-3]
    except:  # 捕获所有可能的转换错误
        return f"{raw_ts_str}"  # 出错则显示原始值


def create_instrument_management_card(
        inst_config: dict,
        on_toggle_enable: Callable[[Dict[str, Any], bool], Coroutine[Any, Any, None]],
        on_remove: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
):
    # 创建一个包含管理功能的交易对价格显示卡片。
    inst_id = inst_config["instId"]
    # channel = inst_config["channel"] # 当前UI卡片不直接显示channel
    is_enabled = inst_config.get("enabled", True)

    storage_prefix = inst_id.lower().replace('-', '_')

    with ui.card().classes('w-72 m-2 shadow-md rounded-lg'):  # 卡片容器
        with ui.row().classes('w-full items-center justify-between p-2 bg-gray-100 rounded-t-lg'):
            ui.label(inst_id).classes('text-md font-semibold')  # 交易对ID作为标题
            with ui.row().classes('items-center'):  # 管理按钮行
                ui.switch(value=is_enabled, on_change=lambda e: on_toggle_enable(inst_config, e.value)) \
                    .props('dense size=sm color=positive') \
                    .tooltip(text="启用/禁用此交易对的实时数据订阅")
                ui.button(icon='delete_outline', on_click=lambda: on_remove(inst_config)) \
                    .props('flat dense round color=negative size=sm') \
                    .tooltip(text="从此列表移除此交易对")

        with ui.card_section().classes('p-2'):  # 价格和时间戳显示区域
            # 价格标签，仅在启用时可见
            price_display_container = ui.row().classes('w-full items-center')
            with price_display_container:
                ui.label().classes('text-base').bind_text_from(
                    app.storage.user, f'{storage_prefix}_mark_price',
                    backward=lambda x: f"价格: {x if x is not None and x != '---' else '---'}"
                ).bind_visibility_from(inst_config, 'enabled')  # 根据inst_config的enabled状态绑定可见性

                ui.label("已禁用").classes('text-base text-gray-400 italic').bind_visibility_from(
                    inst_config, 'enabled', backward=lambda e_status: not e_status
                )  # “已禁用”标签，与enabled状态相反

            # 时间戳标签，仅在启用时可见
            ts_display_container = ui.row().classes('w-full items-center mt-1')
            with ts_display_container:
                ui.label().classes('text-xs text-gray-500').bind_text_from(
                    app.storage.user, f'{storage_prefix}_timestamp',
                    backward=_format_timestamp_for_display
                ).bind_visibility_from(inst_config, 'enabled')