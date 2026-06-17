"""MutguiRoute — 同路径 HTTP + WebSocket 路由组件。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from mutgui import ModuleRegistry, View as GUIView

DEFAULT_RUNTIME_IMPORTS = ("@mutgui/antd", "@mutgui/html")
DEFAULT_RUNTIME_INSTALLS = ("@mutgui/theme-dark",)
LayoutMode = Literal["plain", "centered", "fullscreen"]

MODULE_REGISTRY = ModuleRegistry()
MODULE_REGISTRY.add_from_package("mutgui")
DEFAULT_RUNTIME_CSS = tuple(MODULE_REGISTRY.runtime_manifest()["css"])


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def mutgui_runtime_assets() -> str:
    runtime_manifest = MODULE_REGISTRY.runtime_manifest()
    import_map = {"imports": runtime_manifest["importMap"]}
    return f'  <script type="importmap">{_json_script(import_map)}</script>'


def mutgui_boot_script() -> str:
    return f'  <script src="{MODULE_REGISTRY.url_for("mutgui", "boot.js")}"></script>'


def mutgui_mount_div(
    *,
    ws_path: str | None = None,
    extra_attrs: str = "",
) -> str:
    attrs = ["data-mutgui-app"]
    if ws_path is not None:
        attrs.append(f'data-ws-url="{ws_path}"')
    if extra_attrs:
        attrs.append(extra_attrs.strip())
    return f"<div {' '.join(attrs)}></div>"


def _head_extra_for_layout(layout: LayoutMode) -> str:
    viewport = '  <meta name="viewport" content="width=device-width, initial-scale=1">'
    if layout == "fullscreen":
        return f"""
{viewport}
  <style>
    html, body, #app {{ height: 100%; margin: 0; }}
    body {{ overflow: hidden; }}
  </style>"""
    return viewport


def _body_markup_for_layout(mount_div: str, layout: LayoutMode) -> str:
    if layout == "centered":
        return f"""  <div style="max-width: 960px; margin: 40px auto; padding: 0 12px; font-family: sans-serif;">
    {mount_div}
  </div>"""
    return f"  {mount_div}"


def mutgui_page(
    title: str,
    ws_path: str | None = None,
    *,
    layout: LayoutMode = "plain",
) -> str:
    """生成标准 mutgui HTML 页面。

    ws_path 为 None 时使用当前页面路径（同路径 WebSocket）。
    """
    mount_div = mutgui_mount_div(ws_path=ws_path, extra_attrs='id="app"')
    body_markup = _body_markup_for_layout(mount_div, layout)

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title} — mutgui</title>
{_head_extra_for_layout(layout)}
</head>
<body>
{body_markup}
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
        layout: LayoutMode = "plain",
        runtime_imports: Sequence[str] = DEFAULT_RUNTIME_IMPORTS,
        runtime_installs: Sequence[str] = DEFAULT_RUNTIME_INSTALLS,
        runtime_css: Sequence[str] = DEFAULT_RUNTIME_CSS,
    ) -> None:
        super().__init__()
        self.path = path
        self.view = view
        self._title = title or "mutgui"
        self._html = html
        self._layout = layout
        self._runtime_imports = tuple(runtime_imports)
        self._runtime_installs = tuple(runtime_installs)
        self._runtime_css = tuple(runtime_css)

    def get_html(self) -> str:
        if self._html is not None:
            return self._html
        return mutgui_page(self._title, layout=self._layout)

    def runtime_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for href in self._runtime_css:
            messages.append({"type": "runtime.css", "href": href})
        for name in self._runtime_imports:
            messages.append({"type": "runtime.import", "module": name})
        for name in self._runtime_installs:
            messages.append({"type": "runtime.install", "module": name})
        messages.append({"type": "runtime.mount"})
        return messages


class DemoApp:
    """Demo 应用容器。Gallery 通过 app.routes 发现路由，独立运行通过 app.run()。"""

    def __init__(self, routes: list[MutguiRoute]) -> None:
        super().__init__()
        self.routes = routes

    def run(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        debug: bool = False,
    ) -> None:
        from ._server import run_single
        run_single(self, host=host, port=port, debug=debug)
