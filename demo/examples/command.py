"""command channel demo — 从后端触发浏览器导航副作用。"""

from __future__ import annotations

from mutgui import View, ViewBlock, Callback, PerViewport

from demo.framework import MutguiRoute, DemoApp


class CommandHomeView(View):
    async def _redirect(self) -> None:
        await self.send_command("mutgui.redirect", url="redirected/")

    async def _replace(self) -> None:
        await self.send_command("mutgui.redirect", url="replaced/", replace=True)

    async def _reload(self) -> None:
        await self.send_command("mutgui.reload")

    async def _missing(self) -> None:
        await self.send_command("mutgui.missing", source="demo")

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "html.div",
                "$id": "wrap",
                "style": {
                    "padding": "24px",
                    "fontFamily": "system-ui",
                    "maxWidth": "720px",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "12px",
                },
                "$children": [
                    {"$component": "html.h2", "$id": "title", "children": "Protocol Command Channel Demo"},
                    {
                        "$component": "html.p",
                        "$id": "desc",
                        "children": "按钮点击先到后端，再由后端通过 command 通道要求浏览器执行导航原语。",
                    },
                    {
                        "$component": "html.p",
                        "$id": "connection-id",
                        "children": PerViewport(lambda vid: f"当前连接 channel_id：{vid}"),
                    },
                    {
                        "$component": "html.div",
                        "$id": "actions",
                        "style": {
                            "display": "flex",
                            "flexWrap": "wrap",
                            "gap": "8px",
                        },
                        "$children": [
                            {
                                "$component": "html.button",
                                "$id": "redirect",
                                "children": "后端触发 redirect",
                                "onClick": Callback(self._redirect),
                            },
                            {
                                "$component": "html.button",
                                "$id": "replace",
                                "children": "后端触发 replace redirect",
                                "onClick": Callback(self._replace),
                            },
                            {
                                "$component": "html.button",
                                "$id": "reload",
                                "children": "后端触发 reload",
                                "onClick": Callback(self._reload),
                            },
                            {
                                "$component": "html.button",
                                "$id": "missing",
                                "children": "发送未知命令（看 console warning）",
                                "onClick": Callback(self._missing),
                            },
                        ],
                    },
                    {
                        "$component": "html.ul",
                        "$id": "notes",
                        "$children": [
                            {"$component": "html.li", "$id": "note-redirect",
                             "children": "redirected/ 页面会演示 history(-1) 返回上一页。"},
                            {"$component": "html.li", "$id": "note-replace",
                             "children": "replaced/ 页面会说明 replace 覆盖当前 history 记录。"},
                            {"$component": "html.li", "$id": "note-reload",
                             "children": "reload 会重新建立当前 websocket 连接，因此 channel_id 会变化。"},
                        ],
                    },
                ],
            },
        ])


class CommandTargetView(View):
    title: str
    description: str
    show_history_back: bool

    def __init__(
        self, *, title: str, description: str, show_history_back: bool,
    ) -> None:
        super().__init__()
        self.title = title
        self.description = description
        self.show_history_back = show_history_back

    async def _history_back(self) -> None:
        await self.send_command("mutgui.history", delta=-1)

    async def _go_home(self) -> None:
        await self.send_command("mutgui.redirect", url="../")

    async def _reload(self) -> None:
        await self.send_command("mutgui.reload")

    def render(self) -> ViewBlock:
        actions: list[dict[str, object]] = [
            {
                "$component": "html.button",
                "$id": "home",
                "children": "用普通 redirect 回到首页",
                "onClick": Callback(self._go_home),
            },
            {
                "$component": "html.button",
                "$id": "reload",
                "children": "后端触发 reload",
                "onClick": Callback(self._reload),
            },
        ]
        if self.show_history_back:
            actions.insert(0, {
                "$component": "html.button",
                "$id": "history-back",
                "children": "后端触发 history(-1)",
                "onClick": Callback(self._history_back),
            })
        return ViewBlock([
            {
                "$component": "html.div",
                "$id": "wrap",
                "style": {
                    "padding": "24px",
                    "fontFamily": "system-ui",
                    "maxWidth": "720px",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "12px",
                },
                "$children": [
                    {"$component": "html.h2", "$id": "title", "children": self.title},
                    {"$component": "html.p", "$id": "desc", "children": self.description},
                    {"$component": "html.p", "$id": "connection-id",
                     "children": PerViewport(lambda vid: f"当前连接 channel_id：{vid}"),
                    },
                    {
                        "$component": "html.div",
                        "$id": "actions",
                        "style": {
                            "display": "flex",
                            "flexWrap": "wrap",
                            "gap": "8px",
                        },
                        "$children": actions,
                    },
                ],
            },
        ])


app = DemoApp([
    MutguiRoute("/", CommandHomeView(), title="Command Channel", layout="plain"),
    MutguiRoute(
        "/redirected/",
        CommandTargetView(
            title="Redirect Target",
            description="这是普通 redirect 到达的目标页；这里可以直接演示 history(-1) 返回来源页。",
            show_history_back=True,
        ),
        title="Command Redirect Target",
        layout="plain",
    ),
    MutguiRoute(
        "/replaced/",
        CommandTargetView(
            title="Replace Redirect Target",
            description="这是 replace redirect 到达的目标页；当前 history 记录已被覆盖，因此不再展示 history(-1) 返回按钮。",
            show_history_back=False,
        ),
        title="Command Replace Target",
        layout="plain",
    ),
])


if __name__ == "__main__":
    app.run()
