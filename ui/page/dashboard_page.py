import asyncio
import logging
from nicegui import ui, app

# 项目内部导入
from ws_util.public_channel_manager import PublicChannelManager
from ui.component.trading_pair_card import TradingPairCard
import db_manager  # 新增：数据库管理器
from app_models import TradingPair  # 新增：数据模型

logger = logging.getLogger(__name__)

# 全局变量或使用 app.state 来管理核心服务实例
pcm_instance: PublicChannelManager | None = None
trading_pair_cards: dict[str, TradingPairCard] = {}  # 通过 instId 存储卡片实例
cards_container: ui.grid | None = None  # 新增: 使cards_container在回调中可访问


def price_update_handler_factory(id_to_update: str):  # 移到外部，使其可被多处调用
    """为指定instId创建价格更新回调处理函数。"""

    def handler(price: str):
        logger.debug(f"UI: 收到价格更新 for {id_to_update}: {price}")
        if id_to_update in trading_pair_cards:
            trading_pair_cards[id_to_update].update_price(price)
        else:
            logger.warning(f"UI: 未找到 {id_to_update} 的卡片来更新价格。")

    return handler


async def setup_page_content():
    """构建仪表盘页面的UI元素。"""
    global pcm_instance, cards_container  # 声明全局变量以便赋值

    # 从数据库加载交易对
    # 此时数据库应已初始化，并且如果为空，默认交易对已被添加 (在 on_app_startup 中处理)
    monitored_pairs_from_db = db_manager.get_all_trading_pairs()

    with ui.column().classes('items-center w-full q-pa-md'):
        ui.label("加密货币行情监控").classes('text-3xl font-bold text-primary mb-6')

        # 用于显示交易对卡片的容器
        cards_container = ui.grid(columns=3).classes('gap-4 w-full max-w-4xl')

        # 为从数据库加载的已启用的交易对创建卡片并订阅
        with cards_container:
            for pair_model in monitored_pairs_from_db:
                if pair_model.is_enabled:  # 只处理启用的交易对
                    # 检查卡片是否已存在 (例如，在热重载或部分更新后)
                    if pair_model.instId not in trading_pair_cards:
                        card = TradingPairCard(inst_id=pair_model.instId)
                        trading_pair_cards[pair_model.instId] = card
                        logger.info(f"UI: 为 {pair_model.instId} 创建卡片。")

                        if pcm_instance:
                            # 订阅价格 (resubscribe_check=False 确保在页面加载时尝试订阅)
                            logger.debug(f"UI: 请求订阅 {pair_model.instId}")
                            await pcm_instance.subscribe_mark_price(pair_model.instId, resubscribe_check=False)
                            # 注册价格更新回调
                            pcm_instance.register_price_update_callback(
                                pair_model.instId,
                                price_update_handler_factory(pair_model.instId)
                            )
                    else:
                        # 卡片对象已存在于 trading_pair_cards 字典中
                        # NiceGUI 会处理UI元素的重绘，我们不需要在这里重新添加 card 对象到 cards_container
                        # 但我们可能需要确保订阅和回调是最新的，尽管当前逻辑下它们应该在创建时就设置好了
                        logger.debug(f"UI: {pair_model.instId} 的卡片已存在于字典中。")
                        # 确保订阅仍然有效并注册回调 (以防万一)
                        if pcm_instance:
                            await pcm_instance.subscribe_mark_price(pair_model.instId,
                                                                    resubscribe_check=True)  # check=True 因为可能已订阅
                            pcm_instance.register_price_update_callback(
                                pair_model.instId,
                                price_update_handler_factory(pair_model.instId)
                            )

        # 手动添加交易对的输入区域
        with ui.row(wrap=False).classes('mt-8 items-center gap-x-2'):
            new_inst_id_input = ui.input(label="添加交易对 (例如 BTC-USDT-SWAP)",
                                         placeholder="ETH-USDT-SWAP") \
                .props('outlined dense clearable').classes('flex-grow')

            async def handle_add_pair():
                global cards_container  # 确保在闭包中能访问到 cards_container
                inst_id = new_inst_id_input.value
                if not inst_id:
                    ui.notify("InstId 不能为空!", type='warning', position='top')
                    return

                inst_id = inst_id.strip().upper()
                new_inst_id_input.value = ''  # 清空输入框

                if inst_id in trading_pair_cards:
                    ui.notify(f"{inst_id} 已在监控列表中。", type='info', position='top')
                    return

                # 尝试添加到数据库
                new_pair_model = TradingPair(instId=inst_id, is_enabled=True)  # 默认启用
                pair_db_id = db_manager.add_trading_pair(new_pair_model)

                if pair_db_id is not None:
                    # 添加成功到数据库
                    logger.info(f"UI: {inst_id} 已成功添加到数据库 (ID: {pair_db_id})。")
                    if cards_container is not None:  # 确保容器存在
                        with cards_container:  # 将新卡片添加到同一个容器
                            card = TradingPairCard(inst_id=inst_id, initial_price="待订阅...")
                            trading_pair_cards[inst_id] = card
                    else:
                        logger.error("UI: cards_container 未初始化，无法添加新卡片到UI。")

                    # 订阅并注册回调
                    if pcm_instance:
                        logger.debug(f"UI: 添加新交易对后，请求订阅 {inst_id}")
                        await pcm_instance.subscribe_mark_price(inst_id, resubscribe_check=False)
                        pcm_instance.register_price_update_callback(
                            inst_id,
                            price_update_handler_factory(inst_id)
                        )
                    ui.notify(f"已添加并开始监控 {inst_id}。", type='positive', position='top')
                else:
                    # 添加到数据库失败 (例如，UNIQUE constraint)
                    logger.warning(f"UI: 添加 {inst_id} 到数据库失败。可能已存在。")
                    # 检查是否是因为 instId 已存在于数据库
                    existing_pair = None
                    all_db_pairs = db_manager.get_all_trading_pairs()  # 重新获取以确认
                    for p in all_db_pairs:
                        if p.instId == inst_id:
                            existing_pair = p
                            break

                    if existing_pair:
                        ui.notify(f"{inst_id} 已存在于数据库中。", type='info', position='top')
                        # 如果存在但未在UI显示 (例如之前被禁用或未加载),可以考虑在这里处理加载逻辑
                        # 但当前 `if inst_id in trading_pair_cards:` 应该已覆盖此场景
                    else:
                        ui.notify(f"添加 {inst_id} 到数据库时发生未知错误。", type='error', position='top')

            ui.button("添加监控", on_click=handle_add_pair).props('color=primary icon=add')


async def on_app_startup():
    """NiceGUI应用启动时执行的异步任务。"""
    global pcm_instance
    logging.info("Dashboard: 应用启动中...")

    db_manager.initialize_database()  # 初始化数据库表

    # 检查并添加默认交易对（如果数据库为空）
    all_pairs = db_manager.get_all_trading_pairs()
    if not all_pairs:
        default_pair = TradingPair(instId="BTC-USDT-SWAP", is_enabled=True)
        added_id = db_manager.add_trading_pair(default_pair)
        if added_id:
            logging.info(f"已添加默认交易对 {default_pair.instId} (ID: {added_id}) 到数据库。")
        else:
            # 可能是并发创建或其他问题，如果此时查询仍然为空，则是个问题
            if not db_manager.get_all_trading_pairs():
                logging.error(f"添加默认交易对 {default_pair.instId} 到数据库失败，且数据库仍为空。")
            else:
                logging.info(f"默认交易对 {default_pair.instId} 可能已被其他方式添加。")

    if pcm_instance is None:
        pcm_instance = PublicChannelManager()
    # PCM 启动后，setup_page_content 将负责根据数据库内容进行初始订阅
    asyncio.create_task(pcm_instance.start())  # PublicChannelManager.start() 是非阻塞的
    logging.info("Dashboard: PublicChannelManager 启动任务已创建。")


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

    @ui.page('/')
    async def dashboard_page_builder():
        # trading_pair_cards.clear() # 谨慎：如果页面部分更新，这里清理会导致问题
        # 对于单页应用，如果每次访问都完整重建，也许可以
        # 但更好的做法是让 setup_page_content 处理卡片的添加和更新
        await setup_page_content()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    # db_manager.initialize_database() # 移至 on_app_startup

    create_dashboard_page()

    ui.run(
        title="OKX行情监控仪表盘",
        reload=False,  # reload=True 在开发中可能导致 pcm_instance 和回调的复杂性增加
        port=8080
    )