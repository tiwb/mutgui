"""最简 mutgui 示例 — 一个计数器按钮。"""
from __future__ import annotations

from mutgui import View, ViewBlock, Callback

from demo.framework import MutguiRoute, DemoApp


class CounterView(View):
    def __init__(self) -> None:
        self.count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Typography.Title", "$id": "title",
             "level": 3, "children": "mutgui — Basic Demo"},
            {"$component": "Button", "$id": "btn",
             "type": "primary", "size": "large",
             "children": f"Clicked {self.count} times",
             "onClick": Callback(self._on_click)},
        ])

    def _on_click(self) -> None:
        self.count += 1
        self.invalidate()


app = DemoApp([
    MutguiRoute("/", CounterView(), title="Basic"),
])

if __name__ == "__main__":
    app.run()
