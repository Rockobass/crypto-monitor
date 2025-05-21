# alert_system/rules/price_alert_evaluator.py
import logging
from typing import Dict, Any  # 新增导入
from app_models import AlertRule
from alert_system.rules.base_alert_evaluator import BaseAlertEvaluator

logger = logging.getLogger(__name__)


class PriceAlertEvaluator(BaseAlertEvaluator):
    """
    价格预警评估器。
    评估价格是否达到 '涨超' 或 '跌破' 的阈值。
    """

    def check(self, data: Dict[str, Any], rule: AlertRule) -> bool:
        """
        检查当前价格是否满足价格预警规则。

        参数:
            data (Dict[str, Any]): 当前行情数据，期望包含 'price' 键，其值为浮点数。
                                   例如: {'price': 65000.50}
            rule (AlertRule): 包含 'threshold_price' 和 'condition' 的预警规则。
                              condition 可以是 'above' (涨超) 或 'below' (跌破)。

        返回:
            bool: 如果条件满足则返回 True，否则返回 False。
        """
        if rule.rule_type != "price_alert":
            return False

        current_price = data.get("price")
        if current_price is None or not isinstance(current_price, (float, int)):
            logger.error(f"价格预警规则 '{rule.name}' (ID: {rule.id}) 收到的数据中缺少有效的'price'字段: {data}")
            return False

        # current_price 已经验证是 float 或 int，可以直接使用
        current_price_float = float(current_price)

        try:
            threshold_price = float(rule.params.get("threshold_price"))
            condition = rule.params.get("condition")  # "above" 或 "below"
        except (ValueError, TypeError) as e:
            logger.error(f"规则 '{rule.name}' (ID: {rule.id}) 参数无效: {rule.params}. 错误: {e}")
            return False

        if condition == "above":
            return current_price_float > threshold_price
        elif condition == "below":
            return current_price_float < threshold_price
        else:
            logger.warning(f"规则 '{rule.name}' (ID: {rule.id}) 包含未知条件: {condition}")
            return False