# WsUtil/ConfigPersistence.py
import json
import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "public_subscriptions_config.json")

class ConfigPersistence:
    @staticmethod
    def load_public_subscriptions() -> List[Dict[str, Any]]:
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    if isinstance(config_data, dict) and \
                       isinstance(config_data.get("watched_instruments"), list):
                        valid_instruments = []
                        for item in config_data["watched_instruments"]:
                            if isinstance(item, dict) and "channel" in item and "instId" in item:
                                item.setdefault("enabled", True)
                                valid_instruments.append(item)
                        logger.info(f"配置持久化: 从 {CONFIG_FILE_PATH} 加载 {len(valid_instruments)} 条有效订阅。")
                        return valid_instruments
            else:
                logger.info(f"配置持久化: 文件 {CONFIG_FILE_PATH} 未找到，返回空列表。")
        except Exception as e:
            logger.error(f"配置持久化: 加载配置时出错 {e}，返回空列表。")
        return []

    @staticmethod
    def save_public_subscriptions(watched_instruments: List[Dict[str, Any]]):
        try:
            for item in watched_instruments: item.setdefault("enabled", True)
            config_data = {"watched_instruments": watched_instruments}
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            logger.info(f"配置持久化: {len(watched_instruments)} 条订阅已保存至 {CONFIG_FILE_PATH}。")
        except Exception as e:
            logger.error(f"配置持久化: 保存配置至 {CONFIG_FILE_PATH} 失败 - {e}")