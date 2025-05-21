# ui/component/trading_pair_card.py
from nicegui import ui
from typing import Callable, Awaitable, List, Optional # 新增 List, Optional
from app_models import AlertRule # 新增

class TradingPairCard:
    def __init__(self,
                 inst_id: str,
                 pair_id: int,
                 is_enabled: bool,
                 on_toggle_enable: Callable[[int, str, bool, 'TradingPairCard'], Awaitable[None]],
                 on_delete: Callable[[int, str, 'TradingPairCard'], Awaitable[None]],
                 # 新增预警规则相关的回调
                 on_add_rule: Callable[[int, str], Awaitable[None]], # pair_id, inst_id
                 on_edit_rule: Callable[[AlertRule], Awaitable[None]], # rule_model
                 on_delete_rule: Callable[[int, int], Awaitable[None]], # rule_id, pair_id
                 on_toggle_rule_enabled: Callable[[int, bool, int], Awaitable[None]], # rule_id, new_status, pair_id
                 initial_price: str = "加载中...",
                 initial_rules: Optional[List[AlertRule]] = None): # 初始化时传入规则列表
        self.inst_id = inst_id
        self.pair_id = pair_id
        self._is_enabled = is_enabled
        self.current_price_display: str = ""

        # 预警规则相关回调
        self.on_add_rule_callback = on_add_rule
        self.on_edit_rule_callback = on_edit_rule
        self.on_delete_rule_callback = on_delete_rule
        self.on_toggle_rule_enabled_callback = on_toggle_rule_enabled

        with ui.card().classes('w-72 min-h-[200px]') as self.ui_container: # 稍微加宽卡片
            with ui.card_section():
                ui.label("交易对").classes('text-xs text-gray-500')
                self.inst_id_label = ui.label(self.inst_id).classes('text-lg font-semibold leading-tight')
            with ui.card_section().classes('pt-0'):
                ui.label("当前标记价格").classes('text-xs text-gray-500')
                self.price_label = ui.label().classes('text-2xl font-bold text-blue-600 leading-tight')
                self.price_label.bind_text_from(self, 'current_price_display')

            with ui.card_actions().classes('justify-between items-center'):
                self.enable_switch = ui.switch(
                    value=self._is_enabled,
                    on_change=lambda e: on_toggle_enable(self.pair_id, self.inst_id, e.value, self)
                ).props('dense')
                ui.button(icon='delete', on_click=lambda: on_delete(self.pair_id, self.inst_id, self)) \
                    .props('flat dense color=negative')

            # --- 预警规则区域 ---
            with ui.expansion("预警规则").classes('w-full text-sm').props('dense icon=notifications_active'):
                with ui.card_section().classes('p-2'): # 内部区域使用更紧凑的padding
                    self.rules_container = ui.column().classes('w-full gap-1') # 用于动态添加规则条目
                    if initial_rules:
                        self.update_alert_rules_display(initial_rules)
                    else:
                        with self.rules_container:
                             ui.label("暂无预警规则").classes('text-xs text-gray-400')

                with ui.row().classes('w-full justify-end p-1'):
                    ui.button("添加规则",
                               icon="add_alert",
                               on_click=lambda: self.on_add_rule_callback(self.pair_id, self.inst_id)) \
                        .props('flat dense color=primary text-xs')


            self.update_enabled_status_ui(self._is_enabled, initial_load=True, initial_price_val=initial_price)

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    def update_price(self, price: str):
        if self._is_enabled:
            self.current_price_display = price

    def update_enabled_status_ui(self, new_status: bool, initial_load: bool = False,
                                 initial_price_val: str = "加载中..."):
        self._is_enabled = new_status
        if self.enable_switch.value != new_status:
            self.enable_switch.value = new_status
        self.enable_switch.text = '监控中' if new_status else '已暂停'

        if new_status:
            self.ui_container.classes(remove='opacity-50')
            if self.current_price_display == "已暂停" or initial_load:
                self.current_price_display = initial_price_val if initial_load else "加载中..."
        else:
            self.ui_container.classes(add='opacity-50')
            self.current_price_display = "已暂停"

    def update_alert_rules_display(self, rules: List[AlertRule]):
        """动态更新卡片中显示的预警规则列表"""
        self.rules_container.clear() # 清空现有规则
        with self.rules_container:
            if not rules:
                ui.label("暂无预警规则").classes('text-xs text-gray-400')
                return

            for rule in rules:
                with ui.row().classes('w-full items-center justify-between p-1 border-t'): # 每个规则一行并有上边框
                    with ui.column().classes('gap-0 flex-grow'): # 左侧文字信息
                        ui.label(rule.name or "未命名规则").classes('text-xs font-semibold')
                        ui.label(rule.human_readable_condition or "N/A").classes('text-xxs text-gray-600')
                    with ui.row().classes('gap-0 items-center'): # 右侧操作按钮
                        ui.switch(value=rule.is_enabled,
                                  on_change=lambda e, r=rule: self.on_toggle_rule_enabled_callback(r.id, e.value, self.pair_id)
                                  ).props('dense left-label').classes('mr-1 scale-75 origin-right') # 调整开关样式
                        ui.button(icon='edit',
                                  on_click=lambda r=rule: self.on_edit_rule_callback(r)) \
                            .props('flat dense color=info icon-size=xs p-0 min-w-0 w-6 h-6') # 紧凑按钮
                        ui.button(icon='delete_outline',
                                  on_click=lambda r=rule: self.on_delete_rule_callback(r.id, self.pair_id)) \
                            .props('flat dense color=negative icon-size=xs p-0 min-w-0 w-6 h-6') # 紧凑按钮