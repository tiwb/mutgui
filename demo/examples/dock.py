"""DockPanel 展示 — IDE 风格多面板布局。"""
from __future__ import annotations

from typing import Any

from mutgui import (
    View, ViewBlock, Callback,
    DockPanel, PanelDef, SplitNode, TabSetNode,
)

from demo.framework import DemoApp, MutguiRoute


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
        panels = {
            "explorer":  PanelDef("Explorer",  icon="📁", view=SimplePanelView("explorer", "Explorer")),
            "search":    PanelDef("Search",    icon="🔍", view=SimplePanelView("search", "Search")),
            "git":       PanelDef("Git",       icon="🔀", view=SimplePanelView("git", "Git")),
            "settings":  PanelDef("Settings",  icon="⚙️", view=SimplePanelView("settings", "Settings")),
            "main-py":   PanelDef("main.py",   icon="📄", view=SimplePanelView("main-py", "main.py")),
            "utils-py":  PanelDef("utils.py",  icon="📄", view=SimplePanelView("utils-py", "utils.py")),
            "readme":    PanelDef("README",    icon="📝", view=SimplePanelView("readme", "README")),
            "outline":   PanelDef("Outline",   icon="📋", view=SimplePanelView("outline", "Outline")),
            "problems":  PanelDef("Problems",  icon="⚠️", view=SimplePanelView("problems", "Problems")),
            "output":    PanelDef("Output",    icon="📤", view=SimplePanelView("output", "Output")),
            "terminal":  PanelDef("Terminal",  icon="💻", view=SimplePanelView("terminal", "Terminal")),
        }

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
            ratio=0.2,
        )

        self.dock = DockPanel(id="dock", panels=panels, layout=layout,
                              default_collapse_below=300)

    def render(self) -> ViewBlock:
        return ViewBlock([self.dock])

app = DemoApp([
    MutguiRoute("/", DockView(), title="DockPanel", layout="fullscreen"),
])

if __name__ == "__main__":
    app.run()
