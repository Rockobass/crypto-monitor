from nicegui import ui


@ui.page('/')
def e():
    ui.label('首页')



@ui.page('/index')
def index():
    ui.link('www.baidu.com')

ui.run(port=80, title='nice龟')

