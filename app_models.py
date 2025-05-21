from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


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
    rule_type: str = Field(..., description="预警类型 (e.g., 'price_rise_above', 'kline_pattern')")
    params: Dict[str, Any] = Field(..., description="预警参数 (e.g., {'threshold': 50000})")
    is_enabled: bool = Field(default=True, description="是否启用此规则")
    human_readable_condition: Optional[str] = Field(default=None, description="预警条件的人类可读描述")

    class Config:
        from_attributes = True
