from nicegui import ui


class TradingPairCard:
    def __init__(self, inst_id: str, initial_price: str = "加载中..."):
        self.inst_id = inst_id
        with ui.card().classes('w-64 min-h-[120px]'): # 设置最小高度以保持一致性
            with ui.card_section():
                ui.label("交易对").classes('text-xs text-gray-500')
                self.inst_id_label = ui.label(self.inst_id).classes('text-lg font-semibold leading-tight')
            with ui.card_section().classes('pt-0'): # 减少与上一部分的间距
                ui.label("当前标记价格").classes('text-xs text-gray-500')
                self.price_label = ui.label(initial_price).classes('text-2xl font-bold text-blue-600 leading-tight')

    def update_price(self, price: str):
        self.price_label.set_text(price)

    def set_inst_id(self, inst_id: str): # 万一需要更新instId（虽然通常卡片创建后ID不变）
        self.inst_id_label.set_text(inst_id)