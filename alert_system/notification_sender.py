import json
import requests # 注意：项目中需要安装此库 `pip install requests`
import logging
from config import DINGTALK_WEBHOOK_URL, DINGTALK_KEYWORD # 从config.py导入

logger = logging.getLogger(__name__)


def send_dingtalk_notification(title: str, message: str, inst_id: str, rule_name: str):
    """
    通过钉钉Webhook发送通知。

    参数:
        title (str): 通知标题。
        message (str): 通知消息体。
        inst_id (str): 触发预警的交易对ID。
        rule_name (str): 触发的预警规则名称。
    """
    if not DINGTALK_WEBHOOK_URL:
        logger.warning("钉钉Webhook URL未配置，无法发送通知。")
        print(f"模拟钉钉通知: {title} - {message} (交易对: {inst_id}, 规则: {rule_name})") # 模拟发送
        return

    full_title = f"{DINGTALK_KEYWORD} {title}" # 添加关键词到标题，钉钉机器人安全设置需要
    markdown_text = f"#### {full_title}\n\n**交易对**: {inst_id}\n\n**规则**: {rule_name}\n\n**详情**: {message}\n"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": full_title,
            "text": markdown_text
        },
        "at": {
            "isAtAll": False # 是否@所有人，根据需要调整
        }
    }
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(DINGTALK_WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=10)
        response.raise_for_status() # 如果请求失败 (状态码 4xx or 5xx), 会抛出HTTPError
        result = response.json()
        if result.get("errcode") == 0:
            logger.info(f"钉钉通知发送成功: {title}")
        else:
            logger.error(f"钉钉通知发送失败: {result.get('errmsg')} (错误码: {result.get('errcode')})")
    except requests.exceptions.RequestException as e:
        logger.error(f"发送钉钉通知时发生网络错误: {e}")
    except Exception as e:
        logger.error(f"发送钉钉通知时发生未知错误: {e}")
