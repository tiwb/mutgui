"""DockPanel demo — IDE 风格多面板布局演示。

左侧图标导航栏 + 编辑器 + 右侧属性面板 + 底部输出面板。
支持 tab 切换、拖拽重排、splitter 调整、响应式坍缩。

启动::

    cd mutgui/demo
    python dock_demo.py

然后打开 http://localhost:8081
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from mutgui import (
    View, ViewBlock, ViewPort, Channel, Callback,
    DockPanel, PanelDef, SplitNode, TabSetNode, ActionDef,
)


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------

class WebSocketChannel(Channel):
    def __init__(self, ws: WebSocket) -> None:
        super().__init__()
        self.ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_json(message)


# ---------------------------------------------------------------------------
# 面板内容 View
# ---------------------------------------------------------------------------

class SimplePanelView(View):
    """通用面板内容 — 显示面板名称和简单交互。"""

    def __init__(self, panel_id: str, title: str, color: str = "#f5f5f5") -> None:
        self.id = panel_id
        self.title = title
        self.color = color
        self.click_count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "div", "$id": "wrap",
                "style": {
                    "padding": "16px",
                    "background": self.color,
                    "height": "100%",
                    "boxSizing": "border-box",
                },
                "$children": [
                    {
                        "$component": "div", "$id": "title",
                        "style": {
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "marginBottom": "8px",
                        },
                        "children": self.title,
                    },
                    {
                        "$component": "div", "$id": "info",
                        "style": {"fontSize": "13px", "color": "#666"},
                        "children": f"Clicks: {self.click_count}",
                    },
                    {
                        "$component": "Button", "$id": "btn",
                        "size": "small",
                        "style": {"marginTop": "8px"},
                        "children": "Click me",
                        "onClick": Callback(self._on_click),
                    },
                ],
            },
        ])

    def _on_click(self) -> None:
        self.click_count += 1
        self.invalidate()


# ---------------------------------------------------------------------------
# 根 View — DockPanel 布局
# ---------------------------------------------------------------------------

class RootView(View):
    def __init__(self) -> None:
        panels = [
            PanelDef("explorer", "Explorer", icon="📁"),
            PanelDef("search", "Search", icon="🔍"),
            PanelDef("git", "Git", icon="🔀"),
            PanelDef("settings", "Settings", icon="⚙️"),
            PanelDef("main-py", "main.py", icon="📄"),
            PanelDef("utils-py", "utils.py", icon="📄"),
            PanelDef("readme", "README", icon="📝"),
            PanelDef("outline", "Outline", icon="📋"),
            PanelDef("problems", "Problems", icon="⚠️"),
            PanelDef("output", "Output", icon="📤"),
            PanelDef("terminal", "Terminal", icon="💻"),
        ]

        layout = SplitNode(
            direction="horizontal",
            merge_bars=True,
            collapse_below=500,
            children=(
                TabSetNode(
                    panel_ids=["explorer", "search", "git", "settings"],
                    bar_position="left",
                    display_mode="icon",
                    active_id="explorer",
                ),
                SplitNode(
                    direction="vertical",
                    ratio=0.7,
                    collapse_below=300,
                    children=(
                        SplitNode(
                            direction="horizontal",
                            ratio=0.7,
                            collapse_below=600,
                            children=(
                                TabSetNode(
                                    panel_ids=["main-py", "utils-py", "readme"],
                                    active_id="main-py",
                                ),
                                TabSetNode(
                                    panel_ids=["outline"],
                                    active_id="outline",
                                ),
                            ),
                        ),
                        TabSetNode(
                            panel_ids=["problems", "output", "terminal"],
                            active_id="terminal",
                        ),
                    ),
                ),
            ),
            ratio=0.04,
        )

        self.dock = DockPanel(id="dock", panels=panels, layout=layout)

        colors = {
            "explorer": "#e8f5e9", "search": "#e3f2fd",
            "git": "#fce4ec", "settings": "#fff3e0",
            "main-py": "#ffffff", "utils-py": "#ffffff",
            "readme": "#fffde7", "outline": "#f3e5f5",
            "problems": "#ffebee", "output": "#e0f2f1",
            "terminal": "#263238",
        }
        text_colors = {"terminal": "#4fc3f7"}

        for p in panels:
            color = colors.get(p.id, "#f5f5f5")
            view = SimplePanelView(p.id, p.title, color)
            if p.id in text_colors:
                view.color = color
            self.dock.set_panel_view(p.id, view)

    def render(self) -> ViewBlock:
        return ViewBlock([self.dock])


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

view = RootView()
viewports: list[ViewPort] = []


async def ws_handler(websocket: WebSocket) -> None:
    await websocket.accept()
    vp = ViewPort(view, WebSocketChannel(websocket))
    viewports.append(vp)
    await vp.initialize()
    await view.rendered()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await vp.handle_event(event)
    except Exception:
        pass
    finally:
        vp.detach()
        viewports.remove(vp)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mutgui — DockPanel Demo</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    #app { height: 100vh; display: flex; flex-direction: column; }
    .header {
      padding: 8px 16px; background: #1a1a2e; color: #e0e0e0;
      font-size: 13px; flex-shrink: 0;
      display: flex; align-items: center; gap: 12px;
    }
    .header h3 { font-size: 14px; font-weight: 600; }
    #ws-status { font-size: 11px; opacity: 0.7; }
    .dock-wrap { flex: 1; min-height: 0; overflow: hidden; }
  </style>
</head>
<body>
  <div id="app">
    <div class="header">
      <h3>mutgui DockPanel Demo</h3>
      <span style="opacity:0.6">Drag tabs to reorder | Drag splitters to resize | Resize window to test collapse</span>
      <span style="flex:1"></span>
      <span id="ws-status"></span>
    </div>
    <div class="dock-wrap" id="dock-root"></div>
  </div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/libs/antd.js"></script>
  <script>
    MutguiApp.mount(document.getElementById('dock-root'), `ws://${location.host}/ws`, {
      onStatus: function(s) { document.getElementById('ws-status').textContent = s; }
    });
  </script>
</body>
</html>
"""


async def index(_request: Any) -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "mutgui" / "static"

app = Starlette(routes=[
    Route("/", index),
    WebSocketRoute("/ws", ws_handler),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR))),
])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="127.0.0.1", port=port)
