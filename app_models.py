# app_models.py
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time # 用于 last_triggered_timestamp


class TradingPair(BaseModel):
    # 交易对模型
    id: Optional[int] = Field(default=None, primary_key=True)
    instId: str = Field(..., description="交易对ID，例如 BTC-USDT-SWAP")
    is_enabled: bool = Field(default=True, description="是否启用监控")
    current_price: Optional[str] = Field(default=None, description="当前标记价格 (实时更新，不持久化到DB)")

    class Config:
        from_attributes = True


class AlertRule(BaseModel):
    # 预警规则模型
    id: Optional[int] = Field(default=None, primary_key=True)
    pair_id: int = Field(..., description="关联的TradingPair的ID")
    name: str = Field(..., description="预警规则名称/描述")
    rule_type: str = Field(..., description="预警类型 (e.g., 'price_alert', 'kline_pattern')")
    params: Dict[str, Any] = Field(..., description="预警参数 (e.g., {'threshold_price': 50000, 'condition': 'above'})")
    is_enabled: bool = Field(default=True, description="是否启用此规则")
    human_readable_condition: Optional[str] = Field(default=None, description="预警条件的人类可读描述")
    cooldown_seconds: int = Field(default=60, description="预警冷却时间（秒）")
    last_triggered_timestamp: Optional[float] = Field(default=None, description="此预警最后被触发的时间戳（内存状态）")
    is_threshold_breached: bool = Field(default=False, description="[Internal In-Memory State for Price Alerts] Tracks if the price threshold has been crossed and not yet reset. Not persisted to DB.")

    class Config:
        from_attributes = True

    def is_in_cooldown(self) -> bool:
        """检查预警是否处于冷却状态"""
        if self.last_triggered_timestamp is None:
            return False
        return (time.time() - self.last_triggered_timestamp) < self.cooldown_seconds

    def update_last_triggered(self):
        """更新最后触发时间为当前时间"""
        self.last_triggered_timestamp = time.time()