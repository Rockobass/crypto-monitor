import asyncio
import json
import logging
import websockets
from WebSocketFactory import WebSocketFactory

logger = logging.getLogger(__name__)


class WsPublicAsync:
    def __init__(self, url: str, reconnect_delay: int = 5):
        self.url = url
        self.factory = WebSocketFactory(url)
        self.websocket = None
        self.callback = None
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            logger.warning("当前无运行的事件循环，已创建新循环。如在现有异步上下文中使用，请注意此行为。")
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        self._running = False
        self._reconnect_delay = reconnect_delay
        self._active_subscriptions = []  # 存储活动订阅参数

    async def _connect_websocket(self):
        try:
            self.websocket = await self.factory.connect()
            if self.websocket:
                logger.info("WebSocket 已连接。")
                return True
            # WebSocketFactory.connect 返回 None 的情况已由其内部处理日志
            return False
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            self.websocket = None
            return False

    async def _handle_messages(self):
        try:
            async for message in self.websocket:
                # logger.debug("收到消息: %s", message) # 精简掉debug日志
                if self.callback:
                    try:
                        self.callback(json.loads(message))
                    except json.JSONDecodeError:
                        self.callback(message)  # 非JSON则原始传递
                    # 精简掉回调内部的通用异常捕获日志，依赖调用者处理其回调内部的错误
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket 连接关闭: 代码={e.code}")
        # 精简掉 _handle_messages 内部的通用 Exception 日志，由上层循环处理
        finally:
            # logger.info("消息处理器已结束。") # 精简
            if self.websocket:
                await self.factory.close()
            self.websocket = None

    async def start(self):
        if self._running:
            # logger.info("WebSocket客户端已在运行。") # 精简
            return

        self._running = True
        logger.info("WebSocket客户端启动中...")

        while self._running:
            if await self._connect_websocket():
                if self._active_subscriptions and self.callback:
                    logger.info(f"重新订阅 {len(self._active_subscriptions)} 个频道。")
                    await self._send_operation("subscribe", list(self._active_subscriptions))
                await self._handle_messages()

            if not self._running:  # 检查是否在_handle_messages中被停止
                break

            logger.info(f"{self._reconnect_delay}秒后尝试重连。")
            await asyncio.sleep(self._reconnect_delay)

        logger.info("WebSocket客户端已停止。")

    async def _send_operation(self, op_type: str, args_list: list):
        if not self.websocket or not self.websocket.open:
            # logger.warning(f"无法发送'{op_type}'：未连接。") # 精简
            return
        if not args_list:
            return

        payload = json.dumps({"op": op_type, "args": args_list})
        try:
            await self.websocket.send(payload)
            # logger.info(f"已发送'{op_type}'，参数: {args_list}") # 精简，除非需要详细追踪
        except Exception as e:
            logger.error(f"发送'{op_type}'失败: {e}")

    async def subscribe(self, params: list, callback: callable):
        if not (isinstance(params, list) and all(isinstance(p, dict) for p in params)):
            logger.error("订阅参数'params'必须是字典列表。")
            return
        if not callable(callback):
            logger.error("参数'callback'必须是可调用函数。")
            return

        self.callback = callback
        new_args_to_send = []
        for p_new in params:
            if p_new not in self._active_subscriptions:
                self._active_subscriptions.append(p_new)
                new_args_to_send.append(p_new)

        if new_args_to_send:
            await self._send_operation("subscribe", new_args_to_send)
        # else:
        # logger.info("无新频道需订阅或已激活。") # 精简

    async def unsubscribe(self, params: list):
        if not (isinstance(params, list) and all(isinstance(p, dict) for p in params)):
            logger.error("取消订阅参数'params'必须是字典列表。")
            return

        args_to_send = [p for p in params if p in self._active_subscriptions]

        if args_to_send:
            self._active_subscriptions = [p for p in self._active_subscriptions if p not in args_to_send]
            await self._send_operation("unsubscribe", args_to_send)
        # else:
        # logger.info("无匹配的活动订阅以取消。") # 精简

    async def stop(self):
        logger.info("正在停止WebSocket客户端...")
        self._running = False
        if self.websocket and self.websocket.open:
            await self.factory.close()
        self.websocket = None
        # logger.info("WebSocket客户端停止程序已启动。") # 精简，由start循环退出时打印“已停止”

    def stop_sync(self):
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.stop(), self.loop)
            try:
                future.result(timeout=2)  # 缩短超时
            except TimeoutError:
                logger.error("stop_sync: 等待客户端停止超时。")
            except Exception as e:  # 更简洁的异常处理
                logger.error(f"stop_sync: 停止时出错: {e}")
        else:
            self._running = False
            logger.warning("stop_sync: 事件循环未运行，可能无法完全优雅停止。")