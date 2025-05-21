# WsUtil/PublicSubscriptionManager.py
import logging
from typing import List, Dict, Any
from .PublicConnectionManager import PublicConnectionManager  # 假设已存在且功能稳定
from .ConfigPersistence import ConfigPersistence

logger = logging.getLogger(__name__)


class PublicSubscriptionManager:
    def __init__(self, connection_manager: PublicConnectionManager):
        self.conn_manager = connection_manager
        self._desired_config: List[Dict[str, Any]] = []  # 从文件加载的完整配置
        self._active_on_server: Dict[str, Dict[str, Any]] = {}  # 当前认为服务器上激活的
        self.conn_manager.set_connection_status_callback(self._on_connection_status_changed)
        self._load_initial_config()

    def _load_initial_config(self):
        self._desired_config = ConfigPersistence.load_public_subscriptions()
        logger.info(f"订阅管理器: 初始化加载 {len(self._desired_config)} 条订阅配置。")

    def _get_key(self, arg: Dict[str, Any]) -> str:  # 统一生成key
        return f"{arg.get('channel', '')}|{arg.get('instId', '')}"

    def get_enabled_subscription_args(self) -> List[Dict[str, Any]]:
        # 从当前配置中获取所有应激活的订阅参数（仅channel, instId）
        return [
            {"channel": item["channel"], "instId": item["instId"]}
            for item in self._desired_config if item.get("enabled", True)
        ]

    async def _on_connection_status_changed(self, is_connected: bool):
        if is_connected:
            logger.info("订阅管理器: 连接恢复，同步订阅状态。")
            self._active_on_server.clear()  # 重连后清空本地服务器状态记录
            active_args_to_subscribe = self.get_enabled_subscription_args()
            if active_args_to_subscribe:
                await self.sync_server_subscriptions(active_args_to_subscribe)

    async def _send_ws_operation(self, op_type: str, args_list: List[Dict[str, Any]]):
        if not args_list: return
        await self.conn_manager.send_json_payload({"op": op_type, "args": args_list})

    async def sync_server_subscriptions(self, target_enabled_args: List[Dict[str, Any]]):
        # 根据目标启用的参数列表，更新服务器上的实际订阅
        subs_to_add, subs_to_remove = [], []
        target_keys = {self._get_key(arg) for arg in target_enabled_args}

        # 找出需要新增的订阅
        for arg in target_enabled_args:
            if self._get_key(arg) not in self._active_on_server:
                subs_to_add.append(arg)

        # 找出需要移除的订阅
        current_server_arg_list = list(self._active_on_server.values())  # 当前服务器上的参数列表
        for server_arg in current_server_arg_list:
            if self._get_key(server_arg) not in target_keys:
                subs_to_remove.append(server_arg)

        if subs_to_remove:
            await self._send_ws_operation("unsubscribe", subs_to_remove)
            for arg in subs_to_remove:  # 更新本地服务器状态记录
                self._active_on_server.pop(self._get_key(arg), None)

        if subs_to_add:
            await self._send_ws_operation("subscribe", subs_to_add)
            for arg in subs_to_add:  # 更新本地服务器状态记录
                self._active_on_server[self._get_key(arg)] = arg

        if subs_to_add or subs_to_remove:
            logger.info(f"订阅管理器: 服务端订阅已同步 (新增: {len(subs_to_add)}, 移除: {len(subs_to_remove)})")

    # --- 配置修改方法 (由UI交互触发) ---
    def add_instrument_to_config(self, channel: str, inst_id: str, enabled: bool = True) -> bool:
        key_to_add = self._get_key({"channel": channel, "instId": inst_id})
        if any(self._get_key(item) == key_to_add for item in self._desired_config):
            return False  # 已存在
        self._desired_config.append({"channel": channel, "instId": inst_id, "enabled": enabled})
        ConfigPersistence.save_public_subscriptions(self._desired_config)
        return True

    def remove_instrument_from_config(self, channel: str, inst_id: str) -> bool:
        key_to_remove = self._get_key({"channel": channel, "instId": inst_id})
        original_len = len(self._desired_config)
        self._desired_config = [item for item in self._desired_config if self._get_key(item) != key_to_remove]
        if len(self._desired_config) < original_len:
            ConfigPersistence.save_public_subscriptions(self._desired_config)
            return True
        return False

    def update_instrument_status_in_config(self, channel: str, inst_id: str, enabled: bool) -> bool:
        key_to_update = self._get_key({"channel": channel, "instId": inst_id})
        updated = False
        for item in self._desired_config:
            if self._get_key(item) == key_to_update and item.get("enabled") != enabled:
                item["enabled"] = enabled
                updated = True;
                break
        if updated: ConfigPersistence.save_public_subscriptions(self._desired_config)
        return updated

    def get_all_configured_instruments(self) -> List[Dict[str, Any]]:
        # 返回当前所有配置的副本 (重要：返回副本以避免外部修改)
        return [dict(item) for item in self._desired_config]