"""最简 mutgui 示例 — 一个计数器按钮（纯 HTML，无组件库依赖）。"""
from __future__ import annotations

from mutgui import View, ViewBlock, Callback

from demo.framework import MutguiRoute, DemoApp


class CounterView(View):
    count: int = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "h3", "$id": "title",
             "children": "mutgui — Basic Demo"},
            {"$component": "button", "$id": "btn",
             "style": {"padding": "8px 16px", "fontSize": 16,
                       "cursor": "pointer"},
             "children": f"Clicked {self.count} times",
             "onClick": Callback(self._on_click)},
        ])

    def _on_click(self) -> None:
        self.count += 1
        self.invalidate()


app = DemoApp([
    MutguiRoute("/", CounterView(), title="Basic", layout="plain"),
])

if __name__ == "__main__":
    app.run()
