# ui/component/rule_editor_form.py
from nicegui import ui
from typing import Dict, Any, Callable, Optional, Awaitable
from app_models import AlertRule

# 预警条件选项
CONDITION_OPTIONS = {
    'above': '价格涨超',
    'below': '价格跌破'
}


class RuleEditorForm:
    def __init__(self,
                 trading_pair_id: int,
                 inst_id: str,
                 on_save: Callable[[AlertRule], Awaitable[None]],
                 rule_to_edit: Optional[AlertRule] = None
                 ):
        self.trading_pair_id = trading_pair_id
        self.inst_id = inst_id
        self.on_save_callback = on_save
        self.rule_to_edit = rule_to_edit

        self.dialog = ui.dialog()
        with self.dialog, ui.card().tight():
            ui.card_section().classes('bg-primary text-white')
            dialog_title = f"编辑预警: {rule_to_edit.name}" if rule_to_edit else f"为 {self.inst_id} 添加新预警"
            ui.label(dialog_title).classes('text-lg font-semibold')

            with ui.card_section().classes('w-96'):
                self.rule_name_input = ui.input(
                    label="规则名称",
                    placeholder="例如：BTC突破7万",
                    value=rule_to_edit.name if rule_to_edit else f"{self.inst_id} 价格预警"
                ).props('outlined dense hide-bottom-space').classes('w-full mb-2')

                self.threshold_price_input = ui.number(
                    label="阈值价格 (USDT)",
                    value=float(rule_to_edit.params.get("threshold_price",
                                                        0.0)) if rule_to_edit and rule_to_edit.params else None,
                    # format="%.2f", # <-- 移除了格式化限制
                    step='any'       # <-- 允许输入任意浮点数
                ).props('outlined dense hide-bottom-space').classes('w-full mb-2')

                initial_condition = 'above'
                if rule_to_edit and rule_to_edit.params:
                    loaded_condition = rule_to_edit.params.get("condition")
                    if loaded_condition in CONDITION_OPTIONS:
                        initial_condition = loaded_condition
                    else:
                        print(
                            f"[WARN] RuleEditorForm: Invalid condition '{loaded_condition}' loaded for rule '{rule_to_edit.name if rule_to_edit else 'new rule'}'. Defaulting to 'above'.")

                self.condition_select = ui.select(
                    options=CONDITION_OPTIONS,  # 使用原始字典
                    label="触发条件",
                    value=initial_condition
                ).props('outlined dense map-options hide-bottom-space')

                self.cooldown_input = ui.number(
                    label="冷却时间 (秒)",
                    value=rule_to_edit.cooldown_seconds if rule_to_edit else 60,
                    min=1,
                    step=1
                ).props('outlined dense hide-bottom-space').classes('w-full mb-4')

                self.is_enabled_switch = ui.switch(
                    "启用规则",
                    value=rule_to_edit.is_enabled if rule_to_edit else True
                ).classes('mb-1')

            with ui.card_actions().classes('justify-end px-4 pb-3'):
                ui.button("取消", on_click=self.dialog.close, color='grey').props('flat')
                ui.button("保存", on_click=self.save_rule, color='primary')

    def _generate_human_readable_condition(self, threshold: Optional[float], condition_key: Optional[str]) -> str:
        if threshold is None or condition_key is None:
            return "条件未完整设置"
        condition_text = CONDITION_OPTIONS.get(condition_key, str(condition_key))
        # <-- 修改了格式化，以显示完整的浮点数
        return f"{condition_text} {threshold}"

    async def save_rule(self):
        name_val = self.rule_name_input.value
        threshold_val = self.threshold_price_input.value
        condition_val = self.condition_select.value
        cooldown_val = self.cooldown_input.value
        enabled_val = self.is_enabled_switch.value

        if not name_val or threshold_val is None or condition_val is None or cooldown_val is None:
            ui.notify("所有字段均为必填项！", type='warning')
            return

        if condition_val not in CONDITION_OPTIONS:
            ui.notify(f"选择的条件 '{condition_val}' 无效。请重新选择。", type='error')
            print(
                f"[ERROR] RuleEditorForm.save_rule: Invalid condition_val='{condition_val}' (type: {type(condition_val)}). Expected one of {list(CONDITION_OPTIONS.keys())}.")
            return

        try:
            threshold = float(threshold_val)
            cooldown = int(cooldown_val)
            if cooldown < 1:
                ui.notify("冷却时间必须大于等于1秒！", type='warning')
                return
        except ValueError:
            ui.notify("价格或冷却时间格式不正确！", type='warning')
            return

        params_dict: Dict[str, Any] = {
            "threshold_price": threshold,
            "condition": condition_val
        }

        human_readable = self._generate_human_readable_condition(threshold, condition_val)

        if self.rule_to_edit:
            self.rule_to_edit.name = name_val
            self.rule_to_edit.params = params_dict
            self.rule_to_edit.cooldown_seconds = cooldown
            self.rule_to_edit.is_enabled = enabled_val
            self.rule_to_edit.human_readable_condition = human_readable
            rule_data = self.rule_to_edit
        else:
            rule_data = AlertRule(
                pair_id=self.trading_pair_id,
                name=name_val,
                rule_type="price_alert",
                params=params_dict,
                is_enabled=enabled_val,
                cooldown_seconds=cooldown,
                human_readable_condition=human_readable,
            )

        await self.on_save_callback(rule_data)
        self.dialog.close()

    def open(self):
        self.dialog.open()