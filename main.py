# main_app.py
import asyncio
import logging
from nicegui import app, ui

# 模块导入
from WsUtil.PublicConnectionManager import PublicConnectionManager
from WsUtil.PublicSubscriptionManager import PublicSubscriptionManager
from WsUtil.PublicMessageDispatcher import PublicMessageDispatcher
from modules.MarkPriceLive.MarkPriceProcessor import MarkPriceProcessor
from page.MarkPricePage import build_mark_price_page_layout  # 导入页面布局构建函数

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("CryptoMonitorApp")

OKX_PUBLIC_WS_URL = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"

# --- 应用级单例服务实例 ---
conn_mgr = PublicConnectionManager(url=OKX_PUBLIC_WS_URL)
sub_mgr = PublicSubscriptionManager(connection_manager=conn_mgr)
dispatcher = PublicMessageDispatcher()  # 重命名以匹配调用
mark_price_proc = MarkPriceProcessor()


# --- 应用路由 ---
@ui.page('/')
def route_to_default_page():
    ui.navigate.to('/mark_price_monitor')


@ui.page('/mark_price_monitor')
def mark_price_monitor_page_builder():
    # 调用页面构建函数，并确保传递所有必需的参数
    build_mark_price_page_layout(
        sub_mgr=sub_mgr,
        dispatcher=dispatcher,  # 传递 dispatcher
        mark_price_proc=mark_price_proc  # 传递 mark_price_proc
    )


# --- 应用生命周期 ---
async def on_app_startup():
    logger.info("应用服务初始化 - 启动...")

    conn_mgr.set_message_callback(dispatcher.dispatch)  # dispatcher实例名已修正

    initial_configs = sub_mgr.get_all_configured_instruments()
    for config in initial_configs:
        inst_id, channel = config.get("instId"), config.get("channel")
        if channel == "mark-price" and inst_id:
            dispatcher.register_handler(  # dispatcher实例名已修正
                channel="mark-price",
                inst_id=inst_id,
                handler=mark_price_proc.process_message
            )
            prefix = inst_id.lower().replace('-', '_')
            # 在app.storage.user中为UI绑定预先设置键，确保首次加载时键存在
            # MarkPricePage.py在构建时也会尝试获取这个配置并初始化UI state
            app.storage.user.setdefault(f'{prefix}_mark_price', "---")
            app.storage.user.setdefault(f'{prefix}_timestamp', "---")

    asyncio.create_task(conn_mgr.start())
    logger.info("应用服务初始化 - 完成。")


async def on_app_shutdown():
    logger.info("应用服务清理 - 开始...")
    active_subs = sub_mgr.get_enabled_subscription_args()
    if active_subs:
        await sub_mgr.sync_server_subscriptions([])
        await asyncio.sleep(0.5)
    await conn_mgr.stop()
    logger.info("应用服务清理 - 完成。")


if __name__ in {"__main__", "__mp_main__"}:
    app.on_startup(on_app_startup)
    app.on_shutdown(on_app_shutdown)
    ui.run(
        title="加密货币实时监控",
        port=8080,
        reload=False,
        uvicorn_logging_level='warning',
        storage_secret="CHANGE_THIS_TO_A_REAL_SECRET_KEY"  # 请务必替换为一个真实的强密钥
    )