"""DockPanel 展示 — IDE 风格多面板布局。"""
from __future__ import annotations

from typing import Any

from mutgui import (
    View, ViewBlock, Callback,
    DockPanel, PanelDef, SplitNode, TabSetNode,
)

from demo.framework import MutguiRoute, DemoApp


class SimplePanelView(View):
    title: str = ""
    click_count: int = 0

    def render(self) -> ViewBlock:
        wrap_style: dict[str, Any] = {
            "padding": "16px",
            "height": "100%", "boxSizing": "border-box",
            "color": "var(--mutgui-text)",
        }
        return ViewBlock([{
            "$component": "div", "$id": "wrap",
            "style": wrap_style,
            "$children": [
                {"$component": "div", "$id": "title",
                 "style": {"fontSize": "16px", "fontWeight": "bold", "marginBottom": "8px"},
                 "children": self.title},
                {"$component": "div", "$id": "info",
                 "style": {"fontSize": "13px", "color": "var(--mutgui-text-dim)"},
                 "children": f"Clicks: {self.click_count}"},
                {"$component": "antd.Button", "$id": "btn",
                 "size": "small", "style": {"marginTop": "8px"},
                 "children": "Click me",
                 "onClick": Callback(self._on_click)},
            ],
        }])

    def _on_click(self) -> None:
        self.click_count += 1
        self.invalidate()


class DockView(View):
    def __init__(self) -> None:
        super().__init__()
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
            direction="horizontal", merge_bars=True, collapse_below=500,
            children=(
                TabSetNode(
                    panel_ids=["explorer", "search", "git", "settings"],
                    bar_position="left", display_mode="icon",
                    active_id="explorer",
                ),
                SplitNode(
                    direction="vertical", ratio=0.7, collapse_below=300,
                    children=(
                        SplitNode(
                            direction="horizontal", ratio=0.7, collapse_below=600,
                            children=(
                                TabSetNode(
                                    panel_ids=["main-py", "utils-py", "readme"],
                                    active_id="main-py",
                                ),
                                TabSetNode(panel_ids=["outline"], active_id="outline"),
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

        self.dock = DockPanel(id="dock", panels=panels, layout=layout,
                              default_collapse_below=300)

        for p in panels:
            self.dock.set_panel_view(p.id, SimplePanelView(p.id, p.title))

    def render(self) -> ViewBlock:
        return ViewBlock([self.dock])


DOCK_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mutgui — DockPanel</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    #app { height: 100vh; }
  </style>
</head>
<body>
  <div id="app"></div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/mutgui-antd.js"></script>
  <script src="/static/mutgui-theme-dark.js"></script>
  <script>MutguiApp.mount(document.getElementById('app'), `ws://${location.host}${location.pathname}`, [MutguiThemeDark])</script>
</body>
</html>
"""


app = DemoApp([
    MutguiRoute("/", DockView(), title="DockPanel", html=DOCK_HTML),
])

if __name__ == "__main__":
    app.run()
