# ws_util/public_channel_manager.py
import asyncio # 新增导入
import logging
from typing import Dict, Callable, Any, Set, Optional
from ws_util.ws_client_public import PublicConnectionManager
from config import OKX_WS_URL

logger = logging.getLogger(__name__)


class PublicChannelManager:
    def __init__(self):
        # 初始化WebSocket客户端并设置回调
        self.client = PublicConnectionManager(OKX_WS_URL)
        self.client.set_message_callback(self._on_message) # _on_message 本身是同步方法
        self.client.set_connection_status_callback(self._on_connection_status)

        self._prices: Dict[str, str] = {}
        self._price_update_callbacks: Dict[str, Callable[[str], Any]] = {} # 修改类型提示以接受协程或普通函数
        self._active_subscriptions: Set[str] = set()

    def _on_message(self, message: Any): # _on_message 是一个同步回调
        logger.debug(f"频道管理器收到: {message}")
        if not isinstance(message, dict):
            logger.debug(f"频道管理器收到原始/非字典消息: {message}")
            return

        event = message.get("event")
        arg = message.get("arg", {})
        channel = arg.get("channel")
        inst_id_from_arg = arg.get("instId")

        if not channel or not inst_id_from_arg:
            logger.debug(f"消息缺少 'channel' 或 'instId' 字段: {message}")
            if event == "error":
                logger.error(f"操作错误: {message.get('msg')} (代码: {message.get('code')}) 原始消息: {message}")
            return

        subscription_key = f"{channel}:{inst_id_from_arg}"

        if event == "subscribe":
            logger.info(f"成功订阅频道 '{channel}' instId '{inst_id_from_arg}'")
            self._active_subscriptions.add(subscription_key)
        elif event == "unsubscribe":
            logger.info(f"成功取消订阅频道 '{channel}' instId '{inst_id_from_arg}'")
            self._active_subscriptions.discard(subscription_key)
        elif event == "error":
            logger.error(f"订阅/操作错误: {message.get('msg')} (代码: {message.get('code')}) 参数: {arg}")
        elif channel == "mark-price" and "data" in message and isinstance(message["data"], list):
            for item in message["data"]:
                price_inst_id = item.get("instId")
                mark_px = item.get("markPx")
                if price_inst_id and mark_px:
                    self._prices[price_inst_id] = mark_px
                    logger.debug(f"标记价格更新 for {price_inst_id}: {mark_px}")
                    if price_inst_id in self._price_update_callbacks:
                        callback_fn = self._price_update_callbacks[price_inst_id]
                        # 检查回调是否是协程函数
                        if asyncio.iscoroutinefunction(callback_fn):
                            asyncio.create_task(callback_fn(mark_px)) # <--- 修改点：使用 asyncio.create_task
                        else:
                            callback_fn(mark_px) # 如果不是协程，则直接调用

    async def _on_connection_status(self, is_connected: bool):
        logger.info(f"频道管理器: 连接状态: {'已连接' if is_connected else '已断开'}")
        if is_connected:
            logger.info(f"连接成功，将根据当前UI需求订阅/恢复订阅...")
            desired_inst_ids = list(self._price_update_callbacks.keys())
            self._active_subscriptions.clear()

            if not desired_inst_ids:
                logger.info("当前没有UI请求的交易对需要订阅。")
            else:
                logger.info(f"将为 {len(desired_inst_ids)} 个交易对发起/确认标记价格订阅: {desired_inst_ids}")

            for inst_id in desired_inst_ids:
                await self.subscribe_mark_price(inst_id, resubscribe_check=False)

    async def _send_subscription_op(self, op_type: str, channel: str, inst_id: str) -> bool:
        op_payload = {"op": op_type, "args": [{"channel": channel, "instId": inst_id}]}
        success = await self.client.send_json_payload(op_payload)
        logger.debug(
            f"尝试 {op_type.capitalize()} channel '{channel}' on {inst_id}. 发送状态: {'成功' if success else '失败/排队'}")
        return success

    async def subscribe_mark_price(self, inst_id: str, resubscribe_check: bool = True):
        subscription_key = f"mark-price:{inst_id}"
        if resubscribe_check and subscription_key in self._active_subscriptions:
            logger.info(f"已经订阅 {subscription_key}, 无需重复发送订阅请求。")
            return
        logger.info(f"请求订阅标记价格 for {inst_id}")
        await self._send_subscription_op("subscribe", "mark-price", inst_id)

    async def unsubscribe_mark_price(self, inst_id: str):
        subscription_key = f"mark-price:{inst_id}"
        if inst_id not in self._price_update_callbacks:
            logger.info(f"InstId {inst_id} 已无UI回调, 可能无需取消订阅或已被处理。")
        if subscription_key not in self._active_subscriptions and inst_id not in self._price_update_callbacks:
            logger.info(f"似乎未订阅 {subscription_key} 或UI不关心, 无需发送取消订阅请求。")
        logger.info(f"请求取消订阅标记价格 for {inst_id}")
        await self._send_subscription_op("unsubscribe", "mark-price", inst_id)
        self._active_subscriptions.discard(subscription_key)

    def get_price(self, inst_id: str) -> Optional[str]:
        return self._prices.get(inst_id)

    def register_price_update_callback(self, inst_id: str, callback: Callable[[str], Any]): # 修改类型提示
        self._price_update_callbacks[inst_id] = callback
        current_price = self.get_price(inst_id)
        if current_price: # 如果已有价格，立即使用当前价格回调一次
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(current_price))
            else:
                callback(current_price)


    def unregister_price_update_callback(self, inst_id: str):
        self._price_update_callbacks.pop(inst_id, None)

    async def start(self):
        logger.info("PublicChannelManager: 正在启动底层WebSocket客户端...")
        asyncio.create_task(self.client.start())

    async def stop(self):
        logger.info("PublicChannelManager: 正在停止...")
        await self.client.stop()
        logger.info("PublicChannelManager: 已停止。")