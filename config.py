# OKX WebSocket API URL
OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"  # 公共频道

# 钉钉机器人Webhook
DINGTALK_WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=cd2a9d662831bb588109f8b9b0274d859064b2ef413278801c19a8e6cddc7959"
DINGTALK_KEYWORD = "来啦"

# 数据库文件路径
DATABASE_URL = "sqlite:///./okx_monitor.db" # SQLite数据库文件将创建在项目根目录下

# 日志配置 (后续可以根据需要扩展)
LOG_LEVEL = "INFO"

# K线历史数据缓冲大小 (示例，后续可根据实际需求调整)
KLINE_BUFFER_SIZE = 200