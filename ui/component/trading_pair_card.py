from nicegui import ui
from typing import Callable, Awaitable

class TradingPairCard:
    def __init__(self,
                 inst_id: str,
                 pair_id: int, # 数据库中的ID
                 is_enabled: bool, # 当前是否启用
                 on_toggle_enable: Callable[[int, str, bool, 'TradingPairCard'], Awaitable[None]], # 切换启用状态的回调
                 on_delete: Callable[[int, str, 'TradingPairCard'], Awaitable[None]], # 删除回调
                 initial_price: str = "加载中..."):
        self.inst_id = inst_id
        self.pair_id = pair_id
        self.is_enabled = is_enabled

        # 使用 ui.card() 作为根元素，并保存其实例以便后续操作（如删除）
        with ui.card().classes('w-64 min-h-[160px]') as self.ui_container:
            with ui.card_section():
                ui.label("交易对").classes('text-xs text-gray-500')
                self.inst_id_label = ui.label(self.inst_id).classes('text-lg font-semibold leading-tight')
            with ui.card_section().classes('pt-0'): # 减少与上一部分的间距
                ui.label("当前标记价格").classes('text-xs text-gray-500')
                self.price_label = ui.label(initial_price if self.is_enabled else "已暂停").classes('text-2xl font-bold text-blue-600 leading-tight')

            # 卡片操作区域：启用/禁用开关和删除按钮
            with ui.card_actions().classes('justify-between items-center'): # 使用 justify-between 使元素分布在两端
                self.enable_switch = ui.switch(
                    text='监控中' if self.is_enabled else '已暂停',
                    value=self.is_enabled,
                    on_change=lambda e: on_toggle_enable(self.pair_id, self.inst_id, e.value, self) # e.value 是开关的新状态
                ).props('dense')

                ui.button(icon='delete', on_click=lambda: on_delete(self.pair_id, self.inst_id, self)) \
                    .props('flat dense color=negative')

            # 根据启用状态设置初始透明度
            if not self.is_enabled:
                self.ui_container.classes('opacity-50')


    def update_price(self, price: str):
        if self.is_enabled: # 只在启用时更新价格显示
            self.price_label.set_text(price)
        # else:
            # 如果禁用，可以考虑显示固定文本，但当前逻辑是在创建时和切换时设置
            # self.price_label.set_text("已暂停")

    def set_inst_id(self, inst_id: str): # 万一需要更新instId（虽然通常卡片创建后ID不变）
        self.inst_id_label.set_text(inst_id)

    def update_enabled_status_ui(self, new_status: bool):
        """供外部调用以更新卡片的启用状态相关的UI"""
        self.is_enabled = new_status
        self.enable_switch.value = new_status # 更新开关的实际值
        self.enable_switch.text = '监控中' if new_status else '已暂停' # 更新开关旁边的文本
        if new_status:
            self.ui_container.classes(remove='opacity-50')
            # 如果之前价格是“已暂停”，可能需要请求一次新价格或显示“加载中”
            if self.price_label.text == "已暂停":
                 self.price_label.set_text("加载中...")
        else:
            self.ui_container.classes(add='opacity-50')
            self.price_label.set_text("已暂停") # 禁用时明确显示已暂停