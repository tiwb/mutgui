"""MutguiRoute — 同路径 HTTP + WebSocket 路由组件。"""

from __future__ import annotations

import json
from collections.abc import Sequence

from mutgui import ModuleRegistry, View as GUIView

DEFAULT_PLUGINS = ("@mutgui/theme-dark",)

MODULE_REGISTRY = ModuleRegistry()
MODULE_REGISTRY.add_from_package("mutgui")


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def mutgui_runtime_assets() -> str:
    runtime_manifest = MODULE_REGISTRY.runtime_manifest()
    import_map = {"imports": runtime_manifest["importMap"]}
    return "\n".join([
        f'  <script type="importmap">{_json_script(import_map)}</script>',
        f'  <script id="mutgui-manifest" type="application/json">{_json_script(runtime_manifest)}</script>',
    ])


def mutgui_boot_script() -> str:
    return f'  <script src="{MODULE_REGISTRY.url_prefix("mutgui")}boot.js"></script>'


def mutgui_mount_div(
    *,
    ws_path: str | None = None,
    plugins: Sequence[str] = DEFAULT_PLUGINS,
    extra_attrs: str = "",
) -> str:
    attrs = ["data-mutgui-app"]
    if ws_path is not None:
        attrs.append(f'data-ws-url="{ws_path}"')
    if plugins:
        attrs.append(f'data-plugins="{",".join(plugins)}"')
    if extra_attrs:
        attrs.append(extra_attrs.strip())
    return f"<div {' '.join(attrs)}></div>"


def mutgui_page(
    title: str,
    ws_path: str | None = None,
    *,
    plugins: Sequence[str] = DEFAULT_PLUGINS,
) -> str:
    """生成标准 mutgui HTML 页面。

    ws_path 为 None 时使用当前页面路径（同路径 WebSocket）。
    """
    mount_div = mutgui_mount_div(ws_path=ws_path, plugins=plugins, extra_attrs='id="app"')

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title} — mutgui</title>
</head>
<body>
  <div style="max-width: 960px; margin: 40px auto; font-family: sans-serif;">
    {mount_div}
  </div>
{mutgui_runtime_assets()}
{mutgui_boot_script()}
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
        super().__init__()
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
        super().__init__()
        self.routes = routes

    def run(self, *, host: str = "127.0.0.1", port: int = 8080) -> None:
        from ._server import run_single
        run_single(self, host=host, port=port)
