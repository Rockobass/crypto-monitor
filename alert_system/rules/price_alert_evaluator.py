# alert_system/rules/price_alert_evaluator.py
import logging
from typing import Dict, Any
from app_models import AlertRule
from alert_system.rules.base_alert_evaluator import BaseAlertEvaluator

logger = logging.getLogger(__name__)


class PriceAlertEvaluator(BaseAlertEvaluator):
    """
    价格预警评估器。
    评估价格是否达到 '涨超' 或 '跌破' 的阈值。
    Triggers only on the transition across the threshold.
    """

    def check(self, data: Dict[str, Any], rule: AlertRule) -> bool:
        """
        检查当前价格是否满足价格预警规则。

        参数:
            data (Dict[str, Any]): 当前行情数据，期望包含 'price' 键，其值为浮点数。
                                   例如: {'price': 65000.50}
            rule (AlertRule): 包含 'threshold_price' 和 'condition' 的预警规则。
                              condition 可以是 'above' (涨超) 或 'below' (跌破)。
                              The rule instance will have its 'is_threshold_breached' state updated.

        返回:
            bool: True 如果条件满足预警触发（即阈值被穿越），否则 False。
        """
        if rule.rule_type != "price_alert":
            return False

        current_price_value = data.get("price")
        if current_price_value is None or not isinstance(current_price_value, (float, int)):
            logger.error(f"价格预警规则 '{rule.name}' (ID: {rule.id}) 收到的数据中缺少有效的'price'字段: {data}")
            return False

        current_price_float = float(current_price_value)

        try:
            threshold_price = float(rule.params.get("threshold_price"))
            condition = rule.params.get("condition")  # "above" 或 "below"
        except (ValueError, TypeError) as e:
            logger.error(f"规则 '{rule.name}' (ID: {rule.id}) 参数无效: {rule.params}. 错误: {e}")
            return False

        triggered_now = False

        if condition == "above":
            if not rule.is_threshold_breached:  # If not currently breached (price was at or below threshold)
                if current_price_float > threshold_price:  # Price just crossed above
                    rule.is_threshold_breached = True
                    triggered_now = True
            else:  # Already breached (price was above threshold)
                if current_price_float <= threshold_price:  # Price dropped back to or below threshold (reset)
                    rule.is_threshold_breached = False
                    # No trigger on reset
                # If price is still above and was already breached, no new trigger.
        elif condition == "below":
            if not rule.is_threshold_breached:  # If not currently breached (price was at or above threshold)
                if current_price_float < threshold_price:  # Price just crossed below
                    rule.is_threshold_breached = True
                    triggered_now = True
            else:  # Already breached (price was below threshold)
                if current_price_float >= threshold_price:  # Price rose back to or above threshold (reset)
                    rule.is_threshold_breached = False
                    # No trigger on reset
                # If price is still below and was already breached, no new trigger.
        else:
            logger.warning(f"规则 '{rule.name}' (ID: {rule.id}) 包含未知条件: {condition}")
            return False

        return triggered_now