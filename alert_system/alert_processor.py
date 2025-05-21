# alert_system/alert_processor.py
import logging
import time  # 确保导入 time
from typing import List, Dict, Optional, Any  # 确保导入 Any
from app_models import AlertRule, TradingPair
from db_manager import get_alert_rules_for_pair, get_trading_pair_by_id  # 用于获取规则和交易对信息
from alert_system.rules.price_alert_evaluator import PriceAlertEvaluator
# 未来可以扩展到K线评估器: from alert_system.rules.kline_alert_evaluator import KlineAlertEvaluator
from alert_system.notification_sender import send_dingtalk_notification

logger = logging.getLogger(__name__)


class AlertProcessor:
    def __init__(self):
        self.evaluators = {
            "price_alert": PriceAlertEvaluator(),
            # "kline_pattern": KlineAlertEvaluator(), # 未来扩展
        }
        self._active_rules_by_pair_id: Dict[int, List[AlertRule]] = {}
        self._instId_map: Dict[int, str] = {}

    def load_rules_for_pair(self, pair_id: int, inst_id: str):
        """为指定的交易对加载并缓存其启用的预警规则。"""
        rules_from_db = get_alert_rules_for_pair(pair_id)
        # 确保从数据库加载的规则是 AlertRule 实例，并且具有 last_triggered_timestamp 属性
        # Pydantic 模型在从数据库（通常是字典）创建时，如果 default=None，则该字段存在。
        self._active_rules_by_pair_id[pair_id] = [
            rule for rule in rules_from_db if rule.is_enabled
        ]
        self._instId_map[pair_id] = inst_id
        logger.info(
            f"为交易对 {inst_id} (ID: {pair_id}) 加载了 {len(self._active_rules_by_pair_id[pair_id])} 条启用规则。")

    def remove_rules_for_pair(self, pair_id: int):
        """移除指定交易对的缓存规则。"""
        if pair_id in self._active_rules_by_pair_id:
            del self._active_rules_by_pair_id[pair_id]
        if pair_id in self._instId_map:
            del self._instId_map[pair_id]
        logger.info(f"移除了交易对ID {pair_id} 的缓存规则。")

    def update_rule_in_cache(self, rule: AlertRule):
        """更新或添加单个规则到缓存中。"""
        pair_id = rule.pair_id
        if pair_id not in self._instId_map:
            trading_pair = get_trading_pair_by_id(pair_id)
            if trading_pair:
                self._instId_map[pair_id] = trading_pair.instId
            else:
                logger.warning(f"更新规则缓存失败：找不到pair_id {pair_id} 对应的交易对。")
                return

        if pair_id not in self._active_rules_by_pair_id:
            self._active_rules_by_pair_id[pair_id] = []

        # 确保规则实例是 AlertRule 类型，以便拥有 is_in_cooldown 等方法
        # 如果 rule 不是 AlertRule 实例 (例如，直接从某些外部来源获得字典)，需要先转换
        # 但这里假设传入的 rule 已经是 AlertRule 实例

        # 移除旧规则 (如果存在) 并添加新规则 (如果启用)
        self._active_rules_by_pair_id[pair_id] = [r for r in self._active_rules_by_pair_id[pair_id] if r.id != rule.id]
        if rule.is_enabled:
            # 在添加到缓存前，如果 last_triggered_timestamp 是 None 且规则是从DB新加载的，
            # 它会保持 None 直到第一次触发。
            # 如果是已存在的规则被更新，其内存中的 last_triggered_timestamp 会被保留（如果适用）。
            # 我们的 AlertRule 模型定义中 last_triggered_timestamp default=None，这是正确的。
            self._active_rules_by_pair_id[pair_id].append(rule)

        logger.info(
            f"更新了交易对 {self._instId_map.get(pair_id, '未知')} (ID: {pair_id}) 的规则 (ID: {rule.id}) 缓存。")

    def process_price_data(self, pair_id: int, current_price_str: str):
        """
        处理接收到的标记价格数据，并对照相关规则进行检查。
        """
        if pair_id not in self._active_rules_by_pair_id or pair_id not in self._instId_map:
            trading_pair = get_trading_pair_by_id(pair_id)
            if trading_pair and trading_pair.instId:  # 确保 instId 有效
                self.load_rules_for_pair(pair_id, trading_pair.instId)
            else:
                logger.warning(f"处理价格数据失败：找不到pair_id {pair_id} 对应的交易对或instId。")
                return

        rules_for_pair = self._active_rules_by_pair_id.get(pair_id, [])
        inst_id = self._instId_map.get(pair_id)

        if not rules_for_pair or not inst_id:
            return

        try:
            current_price_float = float(current_price_str)
        except ValueError:
            logger.error(f"无法将价格 '{current_price_str}' 转换为浮点数，交易对: {inst_id}")
            return

        for rule in rules_for_pair:
            if not rule.is_enabled:
                continue

            evaluator = self.evaluators.get(rule.rule_type)
            if not evaluator:
                logger.warning(f"找不到规则类型 '{rule.rule_type}' 的评估器 (规则: {rule.name})")
                continue

            if rule.is_in_cooldown():  # 调用 AlertRule 实例的方法
                logger.debug(f"规则 '{rule.name}' (交易对: {inst_id}) 仍在冷却中，跳过。")
                continue

            market_data_for_evaluator: Dict[str, Any] = {}
            if rule.rule_type == "price_alert":
                market_data_for_evaluator["price"] = current_price_float
            # elif rule.rule_type == "kline_pattern":
            # market_data_for_evaluator["kline_data"] = self.get_kline_data_for_pair(pair_id) # 示例

            try:
                triggered = evaluator.check(market_data_for_evaluator, rule)
            except Exception as e:
                logger.error(f"评估规则 '{rule.name}' (交易对: {inst_id}) 时出错: {e}")
                triggered = False

            if triggered:
                logger.info(f"预警触发! 规则: '{rule.name}', 交易对: {inst_id}, 当前价格: {current_price_float}")

                condition_text = rule.human_readable_condition or f"{rule.params.get('condition')} {rule.params.get('threshold_price')}"
                alert_message = f"当前价格 {current_price_float} {condition_text}."

                send_dingtalk_notification(
                    title=f"价格预警: {inst_id}",
                    message=alert_message,
                    inst_id=inst_id,
                    rule_name=rule.name
                )
                rule.update_last_triggered()  # 调用 AlertRule 实例的方法