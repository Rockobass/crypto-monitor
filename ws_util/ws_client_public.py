import asyncio
import json
import logging
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, ConnectionClosedError
from typing import Callable, Any, List, Optional
from ws_util.WebSocketFactory import WebSocketFactory
from config import OKX_WS_URL

logger = logging.getLogger(__name__)


class PublicConnectionManager:
    def __init__(self, url: str, reconnect_delay: int = 5):
        self.url = url  # WebSocket URL
        self.factory = WebSocketFactory(url)
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None  # 当前的WebSocket连接实例
        self.message_callback: Optional[Callable[[Any], None]] = None  # 收到消息时的回调函数
        self.status_callback: Optional[Callable[[bool], None]] = None  # 连接状态变化时的回调 (True:已连接, False:已断开)
        self._running = False  # 控制客户端运行状态的标志
        self._reconnect_delay = reconnect_delay  # 重连延迟（秒）
        self._pending_sends: List[str] = []  # 存储因未连接而挂起的待发送JSON字符串

    def set_message_callback(self, callback: Callable[[Any], None]):  #
        """设置当收到WebSocket消息时的回调函数。"""
        self.message_callback = callback

    def set_connection_status_callback(self, callback: Callable[[bool], None]):  #
        """设置连接状态变化时的回调函数。"""
        self.status_callback = callback

    async def _connect(self) -> bool:
        """尝试建立WebSocket连接。"""
        logger.debug(f"尝试连接到 {self.url}...")
        try:
            self.websocket = await self.factory.connect()  #
            if self.websocket:
                logger.info(f"已连接到 {self.url}")
                if self.status_callback:
                    asyncio.create_task(self._safe_callback(self.status_callback, True))
                # 连接成功后，发送之前挂起的操作
                if self._pending_sends:
                    logger.info(f"重新发送 {len(self._pending_sends)} 个挂起的操作。")
                    for payload_str in list(self._pending_sends):  # 遍历副本发送
                        if await self.send_json_payload(payload_str, from_pending=True):  #
                            if payload_str in self._pending_sends:  # 再次检查以防并发修改
                                self._pending_sends.remove(payload_str)
                    if self._pending_sends:
                        logger.warning(f"{len(self._pending_sends)} 个操作在重连后仍发送失败。")
                return True
        except Exception as e:
            logger.error(f"连接到 {self.url} 失败: {e}")

        # 连接失败或发生异常
        self.websocket = None
        if self.status_callback:
            asyncio.create_task(self._safe_callback(self.status_callback, False))
        return False

    async def _message_handler_loop(self):
        """处理接收到的消息和心跳。"""
        if not self.websocket:
            return
        try:
            async for message in self.websocket:
                if isinstance(message, str) and message == "ping":  # OKX ping 是字符串 "ping"
                    logger.debug("收到 ping, 发送 pong")
                    await self.send_json_payload("pong")  # OKX 要求回复 "pong" 字符串
                    continue

                if self.message_callback:
                    try:
                        data = json.loads(message)  # 尝试解析JSON
                    except json.JSONDecodeError:
                        data = message  # 非JSON则原始传递
                    asyncio.create_task(self._safe_callback(self.message_callback, data))
        except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError) as e:
            logger.warning(f"WebSocket 连接关闭: {e}")  #
        except Exception as e:
            logger.error(f"消息处理循环中发生错误: {e}", exc_info=True)
        finally:
            logger.info("消息处理循环结束，连接已断开。")
            if self.status_callback:  # 明确通知连接已断开
                asyncio.create_task(self._safe_callback(self.status_callback, False))

            if self.websocket is not None:
                await self.factory.close()  # 使用factory关闭连接
            self.websocket = None

    async def start(self):  #
        """启动客户端并维持连接。"""
        if self._running:
            logger.warning("客户端已在运行中。")
            return
        self._running = True
        logger.info("PublicConnectionManager: 正在启动...")  #

        while self._running:
            # 检查 self.websocket 是否存在，以及其 .closed 状态 (websockets库用 .closed 表示连接已关闭的 future)
            # 为简化，我们主要依赖 _connect 和 _message_handler_loop 的逻辑来管理连接状态
            # 如果 websocket 不存在或上次循环中断开，则尝试连接
            if not self.websocket:
                if not await self._connect():
                    if self._running:
                        logger.info(f"PublicConnectionManager: {self._reconnect_delay}秒后尝试重连。")  #
                        await asyncio.sleep(self._reconnect_delay)
                    continue

            if self.websocket:  # 如果连接成功
                await self._message_handler_loop()  # 此循环会阻塞直到连接断开

            # _message_handler_loop 结束后表示连接已断开
            if self._running:  # 如果仍在运行状态，则准备重连
                logger.info("连接已断开，准备尝试重连...")
                # 在尝试重连前，确保旧的websocket实例已被清理
                if self.websocket is not None:  # 可能在_message_handler_loop的finally中已处理
                    await self.factory.close()
                    self.websocket = None
                await asyncio.sleep(self._reconnect_delay / 2)  # 短暂等待

        logger.info("PublicConnectionManager: 已停止。")  #

    async def send_json_payload(self, payload_dict_or_str: Any, from_pending: bool = False) -> bool:  #
        """发送JSON序列化的数据。payload可以是字典或已经是JSON字符串。"""
        json_str: str
        if isinstance(payload_dict_or_str, str):
            json_str = payload_dict_or_str
        else:
            try:
                json_str = json.dumps(payload_dict_or_str)
            except TypeError as e:
                logger.error(f"无法将payload序列化为JSON: {e} - Payload: {payload_dict_or_str}")
                return False

        # 检查websocket实例是否存在且可用 (这里不直接检查 .closed 或 .state 以保持极简，依赖send的异常)
        if self.websocket:
            try:
                await self.websocket.send(json_str)
                logger.debug(f"已发送: {json_str[:200]}")
                return True
            except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError) as e:
                logger.warning(f"发送时连接已关闭: {e} - 消息: {json_str[:100]}...")
                if self.status_callback:  # 通知连接状态变化
                    asyncio.create_task(self._safe_callback(self.status_callback, False))
            except Exception as e:  # 其他发送错误
                logger.error(f"发送消息失败: {e} - 消息: {json_str[:100]}...")

        # 如果未连接或发送失败，且不是来自暂存队列的重试，则暂存
        if not from_pending:
            if json_str not in self._pending_sends:  # 避免重复添加
                self._pending_sends.append(json_str)
            logger.warning(f"WebSocket未连接或发送失败，操作已暂存: {json_str[:100]}...")  #
        return False

    async def stop(self):  #
        """停止客户端。"""
        logger.info("PublicConnectionManager: 正在停止...")  #
        self._running = False
        if self.websocket:
            await self.factory.close()  # 使用factory关闭
        self.websocket = None
        self._pending_sends.clear()  # 清空待发送队列
        logger.info("PublicConnectionManager: WebSocket已清理。")

    async def _safe_callback(self, callback: Callable, *args):
        """安全地执行回调函数，捕获任何异常。"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"执行回调 {callback.__name__} 时发生错误: {e}", exc_info=True)


# --- 用于独立测试的 main 函数 ---
async def main_test():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    client = PublicConnectionManager(OKX_WS_URL)  # 使用原始类名

    def handle_message(data: Any):
        logger.info(f"收到消息: {data}")

    async def handle_status(is_connected: bool):
        logger.info(f"连接状态: {'已连接' if is_connected else '已断开'}")
        if is_connected:
            sub_payload = {
                "op": "subscribe",
                "args": [{"channel": "mark-price", "instId": "BTC-USDT-SWAP"}]
            }
            await client.send_json_payload(sub_payload)  # 使用原始方法名

    # 为了方便，可以创建一个统一的设置回调的方法，或者分开设置
    client.set_message_callback(handle_message)
    client.set_connection_status_callback(handle_status)

    try:
        await client.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭客户端...")
    finally:
        await client.stop()
        logger.info("测试客户端已完全停止。")


if __name__ == "__main__":
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        logger.info("程序被用户中断。")