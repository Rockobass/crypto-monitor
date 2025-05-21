from nicegui import ui
from typing import Callable, Awaitable


class TradingPairCard:
    def __init__(self,
                 inst_id: str,
                 pair_id: int,
                 is_enabled: bool,
                 on_toggle_enable: Callable[[int, str, bool, 'TradingPairCard'], Awaitable[None]],
                 on_delete: Callable[[int, str, 'TradingPairCard'], Awaitable[None]],
                 initial_price: str = "加载中..."):  # initial_price 用于启用时的初始显示
        self.inst_id = inst_id
        self.pair_id = pair_id
        self._is_enabled = is_enabled  # 内部状态

        # 新增：用于UI绑定的价格显示属性
        self.current_price_display: str = ""  # 初始化为空字符串，由 update_enabled_status_ui 设置初始值

        with ui.card().classes('w-64 min-h-[160px]') as self.ui_container:
            with ui.card_section():
                ui.label("交易对").classes('text-xs text-gray-500')
                self.inst_id_label = ui.label(self.inst_id).classes('text-lg font-semibold leading-tight')
            with ui.card_section().classes('pt-0'):
                ui.label("当前标记价格").classes('text-xs text-gray-500')
                # 将标签的文本绑定到 self.current_price_display 属性
                self.price_label = ui.label().classes('text-2xl font-bold text-blue-600 leading-tight')
                self.price_label.bind_text_from(self, 'current_price_display')

            with ui.card_actions().classes('justify-between items-center'):
                self.enable_switch = ui.switch(
                    value=self._is_enabled,  # 开关的初始值
                    on_change=lambda e: on_toggle_enable(self.pair_id, self.inst_id, e.value, self)
                ).props('dense')
                # 开关文本的更新将由 update_enabled_status_ui 处理

                ui.button(icon='delete', on_click=lambda: on_delete(self.pair_id, self.inst_id, self)) \
                    .props('flat dense color=negative')

            # 调用方法来设置所有初始UI状态，包括价格显示文本和透明度
            self.update_enabled_status_ui(self._is_enabled, initial_load=True, initial_price_val=initial_price)

    @property
    def is_enabled(self) -> bool:
        """公开的只读属性，反映卡片的启用状态。"""
        return self._is_enabled

    def update_price(self, price: str):
        if self._is_enabled:  # 只有启用时才更新可显示的价格
            self.current_price_display = price

    def set_inst_id(self, inst_id: str):
        self.inst_id_label.set_text(inst_id)

    def update_enabled_status_ui(self, new_status: bool, initial_load: bool = False,
                                 initial_price_val: str = "加载中..."):
        """
        集中更新与启用/禁用状态相关的所有UI元素。
        包括：内部状态 _is_enabled, 开关的UI (值和文本), 容器透明度, 以及价格显示文本。
        """
        self._is_enabled = new_status  # 更新内部实际状态

        # 更新开关的视觉状态 (如果其 value 不是直接双向绑定到 self._is_enabled)
        if self.enable_switch.value != new_status:
            self.enable_switch.value = new_status  # 确保开关UI组件的值与新状态同步
        self.enable_switch.text = '监控中' if new_status else '已暂停'  # 更新开关的文本

        # 更新容器样式和价格标签文本 (通过修改 current_price_display 属性，绑定会自动更新UI)
        if new_status:  # 如果要启用
            self.ui_container.classes(remove='opacity-50')
            # 如果是从“已暂停”状态切换过来，或者是在首次加载并启用的情况
            if self.current_price_display == "已暂停" or initial_load:
                # 对于首次加载且启用的情况，使用传入的 initial_price_val
                # 对于从暂停切换到启用的情况，可以显示“加载中”，等待下一次价格更新
                self.current_price_display = initial_price_val if initial_load else "加载中..."
        else:  # 如果要禁用
            self.ui_container.classes(add='opacity-50')
            self.current_price_display = "已暂停"  # 禁用时，价格显示明确为“已暂停”