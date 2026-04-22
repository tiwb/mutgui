"""MutguiRoute — 同路径 HTTP + WebSocket 路由组件。"""

from __future__ import annotations

from mutgui import View as GUIView


def mutgui_page(title: str, ws_path: str | None = None) -> str:
    """生成标准 mutgui HTML 页面。

    ws_path 为 None 时使用 location.pathname（同路径 WebSocket）。
    """
    if ws_path is None:
        ws_url = "`ws://${location.host}${location.pathname}`"
    else:
        ws_url = f"`ws://${{location.host}}{ws_path}`"

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title} — mutgui</title>
</head>
<body>
  <div style="max-width: 960px; margin: 40px auto; font-family: sans-serif;">
    <div id="app"></div>
  </div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/mutgui-antd.js"></script>
  <script>MutguiApp.mount(document.getElementById('app'), {ws_url})</script>
</body>
</html>
"""


class MutguiRoute:
    """同路径同时处理 HTTP GET（返回 HTML）和 WebSocket（ViewPort 生命周期）。

    用法::

        app = DemoApp([
            MutguiRoute("/", my_view, title="Demo"),
            MutguiRoute("/alt", other_view, html=CUSTOM_HTML),
        ])
    """

    def __init__(
        self,
        path: str,
        view: GUIView,
        *,
        title: str | None = None,
        html: str | None = None,
    ) -> None:
        self.path = path
        self.view = view
        self._title = title or "mutgui"
        self._html = html

    def get_html(self) -> str:
        if self._html is not None:
            return self._html
        return mutgui_page(self._title)


class DemoApp:
    """Demo 应用容器。Gallery 通过 app.routes 发现路由，独立运行通过 app.run()。"""

    def __init__(self, routes: list[MutguiRoute]) -> None:
        self.routes = routes

    def run(self, *, host: str = "127.0.0.1", port: int = 8080) -> None:
        from ._server import run_single
        run_single(self, host=host, port=port)
