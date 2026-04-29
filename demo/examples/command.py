"""command channel demo — 从后端触发前端副作用。"""

from __future__ import annotations

from urllib.parse import quote

from mutgui import View, ViewBlock, Callback

from demo.framework import MutguiRoute, DemoApp


class CommandDemoView(View):
    def __init__(self) -> None:
        super().__init__()
        self.logs: list[str] = []
        self.redirect_url = "data:text/html," + quote(
            "<!DOCTYPE html><html><body><h1>mutgui command demo</h1></body></html>",
        )

    async def _redirect(self) -> None:
        await self.send_command("mutgui.redirect", url=self.redirect_url)

    async def _missing(self) -> None:
        self.logs.append("发送不存在的命令，前端应只输出 warning")
        self.logs = self.logs[-6:]
        await self.send_command("mutgui.missing", source="demo")
        self.invalidate()

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "div",
                "$id": "wrap",
                "style": {
                    "padding": "24px",
                    "fontFamily": "system-ui",
                    "margin": "0 auto",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "12px",
                },
                "$children": [
                    {"$component": "h2", "$id": "title", "children": "Protocol Command Channel Demo"},
                    {
                        "$component": "p",
                        "$id": "desc",
                        "children": "按钮点击先到后端，再由后端通过 command 通道要求前端执行副作用。",
                    },
                    {
                        "$component": "div",
                        "$id": "actions",
                        "style": {"display": "flex", "gap": "8px"},
                        "$children": [
                            {
                                "$component": "button",
                                "$id": "redirect",
                                "children": "后端触发 redirect",
                                "onClick": Callback(self._redirect),
                            },
                            {
                                "$component": "button",
                                "$id": "missing",
                                "children": "发送未知命令（看 console warning）",
                                "onClick": Callback(self._missing),
                            },
                        ],
                    },
                    {
                        "$component": "div",
                        "$id": "log-wrap",
                        "style": {
                            "border": "1px solid #ddd",
                            "borderRadius": "6px",
                            "padding": "12px",
                        },
                        "$children": [
                            {"$component": "strong", "$id": "log-title", "children": "日志"},
                            *[
                                {
                                    "$component": "div",
                                    "$id": f"log-{i}",
                                    "children": line,
                                }
                                for i, line in enumerate(self.logs)
                            ],
                        ],
                    },
                ],
            },
        ])


app = DemoApp([
    MutguiRoute("/", CommandDemoView(), title="Command Channel", layout="plain"),
])


if __name__ == "__main__":
    app.run()
