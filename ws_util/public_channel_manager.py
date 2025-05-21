import asyncio
import logging
from typing import Dict, Callable, Any, Set, Optional
from ws_util.ws_client_public import PublicConnectionManager
from config import OKX_WS_URL

logger = logging.getLogger(__name__)


class PublicChannelManager:
    def __init__(self):
        # 初始化WebSocket客户端并设置回调
        self.client = PublicConnectionManager(OKX_WS_URL)
        self.client.set_message_callback(self._on_message)
        self.client.set_connection_status_callback(self._on_connection_status)

        self._prices: Dict[str, str] = {}  # 存储instId对应的价格
        self._price_update_callbacks: Dict[str, Callable[[str], None]] = {}  # instId对应的价格更新回调函数
        self.default_inst_id = "BTC-USDT-SWAP"  # 默认订阅的交易对ID
        self._active_subscriptions: Set[str] = set()  # 跟踪活跃的订阅，格式为 "channel:instId"

    def _on_message(self, message: Any):
        # 处理从WebSocket收到的消息（订阅响应、错误、价格数据等）
        logger.debug(f"频道管理器收到: {message}")
        if not isinstance(message, dict):  # 如果消息不是字典类型，记录并返回
            logger.debug(f"频道管理器收到原始/非字典消息: {message}")
            return

        event = message.get("event")  # 获取事件类型，如 'subscribe', 'error'
        arg = message.get("arg", {})  # 获取参数，通常包含频道和instId
        channel = arg.get("channel")  # 获取频道名称
        inst_id_from_arg = arg.get("instId")  # 获取交易对ID

        if not channel or not inst_id_from_arg:  # 如果关键信息缺失，记录日志并跳过后续处理
            logger.debug(f"消息缺少 'channel' 或 'instId' 字段: {message}")
            # 对于某些错误消息，可能没有arg中的channel和instId，比如登录失败
            if event == "error":
                logger.error(f"操作错误: {message.get('msg')} (代码: {message.get('code')}) 原始消息: {message}")
            return

        subscription_key = f"{channel}:{inst_id_from_arg}"  # 构建唯一的订阅标识

        if event == "subscribe":  # 处理订阅成功事件
            logger.info(f"成功订阅频道 '{channel}' instId '{inst_id_from_arg}'")
            self._active_subscriptions.add(subscription_key)
        elif event == "unsubscribe":  # 处理取消订阅成功事件
            logger.info(f"成功取消订阅频道 '{channel}' instId '{inst_id_from_arg}'")
            self._active_subscriptions.discard(subscription_key)
        elif event == "error":  # 处理错误事件
            logger.error(f"订阅/操作错误: {message.get('msg')} (代码: {message.get('code')}) 参数: {arg}")
        elif channel == "mark-price" and "data" in message and isinstance(message["data"], list):  # 处理标记价格数据推送
            for item in message["data"]:
                price_inst_id = item.get("instId")
                mark_px = item.get("markPx")
                if price_inst_id and mark_px:  # 确保价格数据有效
                    self._prices[price_inst_id] = mark_px  # 更新内部价格缓存
                    logger.debug(f"标记价格更新 for {price_inst_id}: {mark_px}")
                    if price_inst_id in self._price_update_callbacks:  # 如果有UI回调，则调用
                        self._price_update_callbacks[price_inst_id](mark_px)

    async def _on_connection_status(self, is_connected: bool):
        # 处理WebSocket连接状态的变化，连接成功时自动订阅默认交易对
        logger.info(f"频道管理器: 连接状态: {'已连接' if is_connected else '已断开'}")
        if is_connected:
            logger.info(f"连接成功，尝试订阅默认交易对: {self.default_inst_id}")
            # 连接时强制重新订阅，即使之前认为已订阅，因为服务器可能已丢失状态
            await self.subscribe_mark_price(self.default_inst_id, resubscribe_check=False)

    async def _send_subscription_op(self, op_type: str, channel: str, inst_id: str) -> bool:
        # 内部辅助函数：发送订阅或取消订阅的指令到WebSocket
        op_payload = {"op": op_type, "args": [{"channel": channel, "instId": inst_id}]}
        success = await self.client.send_json_payload(op_payload)  #
        log_level = logger.info if success else logger.error  # 根据成功与否选择日志级别
        log_level(f"{op_type.capitalize()} {'成功' if success else '失败'} for channel '{channel}' on {inst_id}")
        return success

    async def subscribe_mark_price(self, inst_id: str, resubscribe_check: bool = True):
        # 公开方法：订阅指定instId的标记价格频道
        subscription_key = f"mark-price:{inst_id}"
        if resubscribe_check and subscription_key in self._active_subscriptions:
            logger.info(f"已经订阅 {subscription_key}, 无需重复发送订阅请求。")
            return
        await self._send_subscription_op("subscribe", "mark-price", inst_id)

    async def unsubscribe_mark_price(self, inst_id: str):
        # 公开方法：取消订阅指定instId的标记价格频道
        subscription_key = f"mark-price:{inst_id}"
        if subscription_key not in self._active_subscriptions:
            logger.info(f"未订阅 {subscription_key}, 无需发送取消订阅请求。")
            return
        await self._send_subscription_op("unsubscribe", "mark-price", inst_id)

    def get_price(self, inst_id: str) -> Optional[str]:
        # 公开方法：获取指定instId的当前缓存价格
        return self._prices.get(inst_id)

    def register_price_update_callback(self, inst_id: str, callback: Callable[[str], None]):
        # 公开方法：为指定instId注册一个价格更新时的回调函数
        self._price_update_callbacks[inst_id] = callback
        current_price = self.get_price(inst_id)
        if current_price:  # 如果已有价格，立即使用当前价格回调一次
            callback(current_price)

    def unregister_price_update_callback(self, inst_id: str):
        # 公开方法：取消注册指定instId的价格更新回调函数
        self._price_update_callbacks.pop(inst_id, None)  # 使用pop并提供默认值None，避免KeyError

    async def start(self):
        # 公开方法：启动底层的WebSocket客户端（它将在后台异步运行）
        logger.info("PublicChannelManager: 正在启动底层WebSocket客户端...")
        asyncio.create_task(self.client.start())  #

    async def stop(self):
        # 公开方法：停止底层的WebSocket客户端
        logger.info("PublicChannelManager: 正在停止...")
        await self.client.stop()  #
        logger.info("PublicChannelManager: 已停止。")