import logging
from typing import Dict, Any
from nicegui import app  # 用于更新UI状态

logger = logging.getLogger(__name__)


class MarkPriceProcessor:
    def __init__(self):
        # 处理标记价格数据，并将其更新到app.storage以供UI使用。
        logger.info("标记价格处理器: 已初始化。")

    def _generate_storage_key_prefix(self, inst_id: str) -> str:
        # 为app.storage生成基于交易对ID的键前缀。
        return inst_id.lower().replace('-', '_')  # 例如 "btc_usdt_swap"

    def process_message(self, message_data: Dict[str, Any]):
        # 处理单个标记价格消息。
        # 期望 message_data 是已经由 Dispatcher 确认过频道类型的完整消息体

        price_updates = message_data.get('data', [])
        if not isinstance(price_updates, list): return

        for price_update in price_updates:
            if not isinstance(price_update, dict): continue

            inst_id = price_update.get('instId')
            mark_px = price_update.get('markPx')
            timestamp = price_update.get('ts')

            if inst_id and mark_px is not None and timestamp is not None:
                prefix = self._generate_storage_key_prefix(inst_id)
                # 更新 app.storage.user (因为是自用程序)
                app.storage.user[f'{prefix}_mark_price'] = mark_px
                app.storage.user[f'{prefix}_timestamp'] = timestamp
                # inst_id 可以选择性存储，如果UI组件直接使用传入的inst_id
                # app.storage.user[f'{prefix}_instrument'] = inst_id