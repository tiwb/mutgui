"""DockPanel 展示 — IDE 风格多面板布局。"""
from __future__ import annotations

from typing import Any

from mutgui import (
    View, ViewBlock, Callback,
    DockPanel, PanelDef, SplitNode, TabSetNode,
)

from demo.framework import MutguiRoute, DemoApp


class SimplePanelView(View):
    def __init__(self, panel_id: str, title: str, color: str = "#f5f5f5") -> None:
        self.id = panel_id
        self.title = title
        self.color = color
        self.click_count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "div", "$id": "wrap",
            "style": {
                "padding": "16px", "background": self.color,
                "height": "100%", "boxSizing": "border-box",
            },
            "$children": [
                {"$component": "div", "$id": "title",
                 "style": {"fontSize": "16px", "fontWeight": "bold", "marginBottom": "8px"},
                 "children": self.title},
                {"$component": "div", "$id": "info",
                 "style": {"fontSize": "13px", "color": "#666"},
                 "children": f"Clicks: {self.click_count}"},
                {"$component": "Button", "$id": "btn",
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

        colors = {
            "explorer": "#e8f5e9", "search": "#e3f2fd",
            "git": "#fce4ec", "settings": "#fff3e0",
            "main-py": "#ffffff", "utils-py": "#ffffff",
            "readme": "#fffde7", "outline": "#f3e5f5",
            "problems": "#ffebee", "output": "#e0f2f1",
            "terminal": "#263238",
        }
        for p in panels:
            color = colors.get(p.id, "#f5f5f5")
            self.dock.set_panel_view(p.id, SimplePanelView(p.id, p.title, color))

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
    html, body { height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--mutgui-bg); color: var(--mutgui-text); }
    #app { height: 100vh; display: flex; flex-direction: column; }
    .header {
      padding: 8px 16px;
      background: var(--mutgui-surface);
      color: var(--mutgui-text);
      border-bottom: 1px solid var(--mutgui-border);
      font-size: 13px; flex-shrink: 0;
      display: flex; align-items: center; gap: 12px;
    }
    .header h3 { font-size: 14px; font-weight: 600; }
    .dock-wrap { flex: 1; min-height: 0; overflow: hidden; }
  </style>
</head>
<body>
  <div id="app">
    <div class="header">
      <h3>mutgui DockPanel Demo</h3>
      <span style="opacity:0.6">Drag tabs | Drag splitters | Resize window</span>
    </div>
    <div class="dock-wrap" id="dock-root"></div>
  </div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/libs/antd.js"></script>
  <script>MutguiApp.mount(document.getElementById('dock-root'), `ws://${location.host}${location.pathname}`)</script>
</body>
</html>
"""


app = DemoApp([
    MutguiRoute("/", DockView(), title="DockPanel", html=DOCK_HTML),
])

if __name__ == "__main__":
    app.run()
