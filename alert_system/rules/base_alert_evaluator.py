# alert_system/rules/base_alert_evaluator.py
from abc import ABC, abstractmethod
from typing import Any, Dict # 修改导入
from app_models import AlertRule

class BaseAlertEvaluator(ABC):
    """
    预警评估器的抽象基类。
    所有具体的规则评估器都必须实现 check 方法。
    """

    @abstractmethod
    def check(self, data: Dict[str, Any], rule: AlertRule) -> bool:
        """
        检查当前数据是否满足预警规则。

        参数:
            data (Dict[str, Any]): 传入的行情数据。
                                   对于价格预警，可能包含 {'price': 70000.0}。
                                   对于K线预警，可能包含 {'kline_data': [...]} 等。
            rule (AlertRule): 预警规则对象。

        返回:
            bool: 如果条件满足则返回 True，否则返回 False。
        """
        pass