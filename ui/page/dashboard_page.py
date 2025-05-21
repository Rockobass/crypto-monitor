import asyncio
import logging
from nicegui import ui, app
from ws_util.public_channel_manager import PublicChannelManager  # 确保路径正确
from ui.component.trading_pair_card import TradingPairCard

# from app_models import TradingPair # 后续用于从数据库加载交易对
# import db_manager # 后续用于通过UI添加交易对到数据库

logger = logging.getLogger(__name__)

# 全局变量或使用 app.state 来管理核心服务实例
pcm_instance: PublicChannelManager | None = None
trading_pair_cards: dict[str, TradingPairCard] = {}  # 通过 instId 存储卡片实例


async def setup_dashboard_content():
    """构建仪表盘页面的UI元素。"""
    global pcm_instance  # 引用全局/app状态的PCM实例

    # 从PCM获取硬编码的instId用于初始显示
    # 在更完整的版本中，我们会从数据库加载instId列表
    initial_inst_id = pcm_instance.hardcoded_inst_id if pcm_instance else "BTC-USDT-SWAP"

    with ui.column().classes('items-center w-full q-pa-md'):  # 使用quasar的padding
        ui.label("加密货币行情监控").classes('text-3xl font-bold text-primary mb-6')

        # 用于显示交易对卡片的容器
        cards_container = ui.grid(columns=3).classes('gap-4 w-full max-w-4xl')

        # 初始时为硬编码的交易对创建卡片
        if initial_inst_id not in trading_pair_cards:  # 确保只创建一次
            with cards_container:
                card = TradingPairCard(inst_id=initial_inst_id)
                trading_pair_cards[initial_inst_id] = card

            # 为此卡片注册价格更新回调
            if pcm_instance:
                # 使用 lambda 确保 inst_id 在回调时是正确的
                # (尽管对于单个硬编码ID，这不那么重要，但对于动态添加是好习惯)
                def price_update_handler_factory(id_to_update: str):
                    def handler(price: str):
                        logger.debug(f"UI: 收到价格更新 for {id_to_update}: {price}")
                        if id_to_update in trading_pair_cards:
                            trading_pair_cards[id_to_update].update_price(price)
                        else:
                            logger.warning(f"UI: 未找到 {id_to_update} 的卡片来更新价格。")

                    return handler

                pcm_instance.register_price_update_callback(
                    initial_inst_id,
                    price_update_handler_factory(initial_inst_id)
                )
        else:  # 如果卡片已存在 (例如页面刷新或重构时)
            with cards_container:  # 需要重新将卡片添加到当前UI树中
                # NiceGUI 在重新运行时会重建UI，所以需要重新添加存在的卡片对象
                # 或者，更好的做法是在每次setup_dashboard_content时重建卡片并重新注册回调
                # 为了简单起见，这里假设卡片对象能被复用或在外部管理
                # 此处逻辑需要根据NiceGUI的页面生命周期和状态管理策略调整
                # 一个更健壮的方法是，如果trading_pair_cards是持久的，
                # 则遍历它并在cards_container中重新“渲染”这些卡片对象
                pass  # 实际应用中这里需要更仔细处理UI元素的重绘

        # 手动添加交易对的输入区域 (第二部分要求有此UI，功能在后续完善)
        with ui.row(wrap=False).classes('mt-8 items-center gap-x-2'):  # wrap=False 避免换行, gap-x-2 水平间距
            new_inst_id_input = ui.input(label="添加交易对 (例如 BTC-USDT-SWAP)",
                                         placeholder="ETH-USDT-SWAP") \
                .props('outlined dense clearable').classes('flex-grow')  # flex-grow 占据多余空间

            async def handle_add_pair():
                inst_id = new_inst_id_input.value
                if not inst_id:
                    ui.notify("InstId 不能为空!", type='warning', position='top')
                    return

                inst_id = inst_id.strip().upper()
                new_inst_id_input.value = ''  # 清空输入框

                if inst_id in trading_pair_cards:
                    ui.notify(f"{inst_id} 已在监控列表中。", type='info', position='top')
                    return

                # 阶段2：仅在UI上添加卡片，不进行实际订阅或数据库操作
                with cards_container:  # 将新卡片添加到同一个容器
                    card = TradingPairCard(inst_id=inst_id, initial_price="待订阅...")
                    trading_pair_cards[inst_id] = card

                ui.notify(f"已在UI添加 {inst_id}。 (真实订阅将在后续实现)", type='positive', position='top')

                # TODO (第3部分):
                # 1. db_manager.add_trading_pair(TradingPair(instId=inst_id))
                # 2. await pcm_instance.subscribe_mark_price(inst_id)
                # 3. pcm_instance.register_price_update_callback(inst_id, price_update_handler_factory(inst_id))

            ui.button("添加监控", on_click=handle_add_pair).props('color=primary icon=add')


async def on_app_startup():
    """NiceGUI应用启动时执行的异步任务。"""
    global pcm_instance
    logging.info("Dashboard: 应用启动中...")
    if pcm_instance is None:
        pcm_instance = PublicChannelManager()
    await pcm_instance.start()  # PublicChannelManager.start() 是非阻塞的
    logging.info("Dashboard: PublicChannelManager 已启动。")


async def on_app_shutdown():
    """NiceGUI应用关闭时执行的异步任务。"""
    global pcm_instance
    logging.info("Dashboard: 应用关闭中...")
    if pcm_instance:
        await pcm_instance.stop()
        logging.info("Dashboard: PublicChannelManager 已停止。")
    trading_pair_cards.clear()  # 清理卡片字典


def create_dashboard_page():
    """注册仪表盘页面和生命周期事件。"""
    app.on_startup(on_app_startup)
    app.on_shutdown(on_app_shutdown)

    # 定义页面路由和内容构建函数
    @ui.page('/')
    async def dashboard():  # 改为异步函数以支持内部可能的await操作
        await setup_dashboard_content()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,  # DEBUG级别可以看到更多PCM和WSClient的日志
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    # db_manager.initialize_database() # 如果添加功能开始使用数据库，则需要初始化

    create_dashboard_page()  # 设置页面和生命周期钩子

    ui.run(
        title="OKX行情监控仪表盘",
        reload=False,  # 开发时可以设为True，但可能需要处理好PCM的重载问题
        port=8080
    )
