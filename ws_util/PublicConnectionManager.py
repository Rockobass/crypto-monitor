import asyncio
import json
import logging
import websockets
from typing import Callable, Any, List, Dict
from .WebSocketFactory import WebSocketFactory


logger = logging.getLogger(__name__)


class PublicConnectionManager:
    def __init__(self, url: str, reconnect_delay: int = 5):
        # 管理公共WebSocket连接，提供重连和原始消息回调。
        self.url = url
        self.factory = WebSocketFactory(url)
        self.websocket = None
        self._message_callback: Callable[[Any], None] = None
        self._connection_status_callback: Callable[[bool], None] = None
        self._loop = asyncio.get_event_loop() # 在init中获取或创建loop
        self._running = False
        self._reconnect_delay = reconnect_delay
        self._pending_send_ops: List[str] = [] # 存储因未连接而挂起的待发送JSON字符串

    def set_message_callback(self, callback: Callable[[Any], None]):
        # 设置当收到WebSocket消息时的回调函数。
        self._message_callback = callback

    def set_connection_status_callback(self, callback: Callable[[bool], None]):
        # 设置连接状态变化时的回调函数。
        self._connection_status_callback = callback

    async def _connect(self):
        # 内部方法：尝试建立连接。
        try:
            self.websocket = await self.factory.connect()
            if self.websocket:
                logger.info("公共连接管理器: WebSocket已连接。")
                if self._connection_status_callback: self._connection_status_callback(True)
                return True
            return False
        except Exception as e:
            logger.error(f"公共连接管理器: WebSocket连接失败 - {e}")
            self.websocket = None
            if self._connection_status_callback: self._connection_status_callback(False)
            return False

    async def _message_loop(self):
        # 内部方法：循环处理接收到的消息。
        try:
            async for message in self.websocket:
                if self._message_callback:
                    try:
                        self._message_callback(json.loads(message))
                    except json.JSONDecodeError:
                        self._message_callback(message) # 非JSON则原始传递
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"公共连接管理器: WebSocket连接关闭 - 代码={e.code}")
        except Exception as e:
            logger.error(f"公共连接管理器: 消息处理时发生意外错误 - {e}")
        finally:
            if self._connection_status_callback: self._connection_status_callback(False)
            if self.websocket: await self.factory.close()
            self.websocket = None

    async def start(self):
        # 启动并维持连接。
        if self._running: return
        self._running = True
        logger.info("公共连接管理器: 正在启动...")

        while self._running:
            if await self._connect():
                # 重连成功后，发送之前挂起的操作
                if self._pending_send_ops:
                    logger.info(f"公共连接管理器: 重新发送 {len(self._pending_send_ops)} 个挂起操作。")
                    for op_payload_str in list(self._pending_send_ops): # 遍历副本发送
                        if await self.send_json_payload(op_payload_str, from_pending=True):
                            if op_payload_str in self._pending_send_ops: # 再次检查以防并发修改
                                self._pending_send_ops.remove(op_payload_str)
                    # 如果仍有未发送成功的，可以选择保留或记录错误
                    if self._pending_send_ops:
                         logger.warning(f"公共连接管理器: {len(self._pending_send_ops)} 个操作在重连后仍发送失败。")


                await self._message_loop()
            if not self._running: break
            logger.info(f"公共连接管理器: {self._reconnect_delay}秒后尝试重连。")
            await asyncio.sleep(self._reconnect_delay)
        logger.info("公共连接管理器: 已停止。")

    async def send_json_payload(self, payload_dict_or_str: Any, from_pending: bool = False) -> bool:
        # 发送JSON序列化后的指令到WebSocket。
        if not self.websocket or not self.websocket.open:
            payload_str = payload_dict_or_str if isinstance(payload_dict_or_str, str) else json.dumps(payload_dict_or_str)
            if not from_pending and payload_str not in self._pending_send_ops: # 避免重复添加
                self._pending_send_ops.append(payload_str)
                logger.warning(f"公共连接管理器: WebSocket未连接，操作已暂存: {payload_str[:100]}...")
            return False
        try:
            payload_to_send = payload_dict_or_str if isinstance(payload_dict_or_str, str) else json.dumps(payload_dict_or_str)
            await self.websocket.send(payload_to_send)
            return True
        except Exception as e:
            logger.error(f"公共连接管理器: 发送指令失败 - {e}")
            # 发送失败时也可以考虑暂存，但要注意避免无限暂存已失败的指令
            return False

    async def stop(self):
        # 停止连接管理器。
        logger.info("公共连接管理器: 正在停止...")
        self._running = False
        if self.websocket and self.websocket.open: await self.factory.close()
        self.websocket = None