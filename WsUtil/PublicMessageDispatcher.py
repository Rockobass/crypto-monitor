import logging
from typing import Callable, Dict, Any, List

logger = logging.getLogger(__name__)


class PublicMessageDispatcher:
    def __init__(self):
        # 分发公共WebSocket消息到已注册的特定频道处理器。
        # 键: "channel|instId" 或 "channel" (对于无instId的频道)
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def _get_handler_key(self, channel: str, inst_id: str = None) -> str:
        # 根据频道和交易对ID生成处理器查找键。
        return f"{channel}|{inst_id}" if inst_id else channel

    def register_handler(self, channel: str, inst_id: str, handler: Callable[[Dict[str, Any]], None]):
        # 注册处理器。inst_id可以为None，表示处理该频道所有instId的消息（如果未找到更精确匹配）。
        key = self._get_handler_key(channel, inst_id)
        self._handlers.setdefault(key, []).append(handler)
        # logger.info(f"公共消息分发器: 已为 {key} 注册处理器 {getattr(handler, '__name__', repr(handler))}")

    def dispatch(self, message: Dict[str, Any]):
        # 分发收到的消息。
        if 'event' in message: return  # 事件消息通常由订阅管理器层面处理或忽略

        arg_data = message.get('arg')
        if not isinstance(arg_data, dict): return

        channel = arg_data.get('channel')
        inst_id = arg_data.get('instId')  # 可能为None

        if not channel: return

        # 优先尝试精确匹配 (channel + instId)
        specific_key = self._get_handler_key(channel, inst_id)
        handlers_found = False
        if specific_key in self._handlers:
            for handler_func in self._handlers[specific_key]:
                try:
                    handler_func(message)
                except Exception as e:
                    logger.error(f"公共消息分发器: 调用处理器处理 {specific_key} 时出错 - {e}")
            handlers_found = True

        # 如果没有精确匹配的instId处理器，且instId存在，尝试匹配通用的频道处理器 (只匹配channel)
        if inst_id and not handlers_found:
            general_channel_key = self._get_handler_key(channel)  # key like "mark-price"
            if general_channel_key in self._handlers:
                for handler_func in self._handlers[general_channel_key]:
                    try:
                        handler_func(message)
                    except Exception as e:
                        logger.error(f"公共消息分发器: 调用通用频道处理器处理 {general_channel_key} 时出错 - {e}")