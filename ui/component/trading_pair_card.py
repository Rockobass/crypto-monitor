from nicegui import ui
from typing import Callable, Awaitable


class TradingPairCard:
    def __init__(self,
                 inst_id: str,
                 pair_id: int,
                 is_enabled: bool,
                 on_toggle_enable: Callable[[int, str, bool, 'TradingPairCard'], Awaitable[None]],
                 on_delete: Callable[[int, str, 'TradingPairCard'], Awaitable[None]],
                 initial_price: str = "加载中..."):
        self.inst_id = inst_id
        self.pair_id = pair_id
        self._is_enabled = is_enabled  # 使用内部变量存储状态，通过方法更新

        with ui.card().classes('w-64 min-h-[160px]') as self.ui_container:
            with ui.card_section():
                ui.label("交易对").classes('text-xs text-gray-500')
                self.inst_id_label = ui.label(self.inst_id).classes('text-lg font-semibold leading-tight')
            with ui.card_section().classes('pt-0'):
                ui.label("当前标记价格").classes('text-xs text-gray-500')
                # 初始价格标签的文本由 update_enabled_status_ui 控制，或直接在此设置
                self.price_label = ui.label("").classes('text-2xl font-bold text-blue-600 leading-tight')

            with ui.card_actions().classes('justify-between items-center'):
                # 开关的值直接绑定到 self.is_enabled 属性 (如果NiceGUI支持双向绑定到属性)
                # 或者通过 on_change 更新并通过方法设置
                self.enable_switch = ui.switch(
                    # text 参数可以动态更新，或者完全移除依赖纯图标/颜色
                    value=self._is_enabled,  # 初始值
                    on_change=lambda e: on_toggle_enable(self.pair_id, self.inst_id, e.value, self)
                ).props('dense')
                ui.button(icon='delete', on_click=lambda: on_delete(self.pair_id, self.inst_id, self)) \
                    .props('flat dense color=negative')

            # 初始化UI状态
            self.update_enabled_status_ui(self._is_enabled, initial_load=True, initial_price_val=initial_price)

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    def update_price(self, price: str):
        if self._is_enabled:
            self.price_label.set_text(price)

    def set_inst_id(self, inst_id: str):
        self.inst_id_label.set_text(inst_id)

    def update_enabled_status_ui(self, new_status: bool, initial_load: bool = False,
                                 initial_price_val: str = "加载中..."):
        """更新卡片的启用状态相关的UI。"""
        self._is_enabled = new_status  # 更新内部状态

        # 更新开关组件的状态（如果它不直接绑定到 self._is_enabled）
        if self.enable_switch.value != new_status:
            self.enable_switch.value = new_status
        self.enable_switch.text = '监控中' if new_status else '已暂停'

        # 更新容器样式和价格标签文本
        if new_status:
            self.ui_container.classes(remove='opacity-50')
            # 只有在状态从“已暂停”变为“监控中”时，或首次加载且启用时，才设置价格文本
            if self.price_label.text == "已暂停" or (initial_load and new_status):
                self.price_label.set_text(initial_price_val if initial_load else "加载中...")
        else:
            self.ui_container.classes(add='opacity-50')
            self.price_label.set_text("已暂停")