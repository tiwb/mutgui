"""Theming demo — 后端控制 none/dark 两种主题模式并通过 reload 切换。"""
from __future__ import annotations

from typing import Literal

from mutgui import View, ViewBlock, Callback, PerViewport

from demo.framework import DemoApp, MutguiRoute

ThemeMode = Literal["none", "dark"]


class ThemingDemoView(View):
    click_count: int = 0
    theme_mode: ThemeMode = "none"

    async def _use_none(self) -> None:
        self.theme_mode = "none"
        await self.send_command("mutgui.reload")

    async def _use_dark(self) -> None:
        self.theme_mode = "dark"
        await self.send_command("mutgui.reload")

    def _on_click(self) -> None:
        self.click_count += 1
        self.invalidate()

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "Theming — 后端控制主题"},
            {"$component": "antd.Typography.Paragraph", "$id": "desc",
             "children": (
                 "这个 demo 只保留 none / dark 两种模式。点击按钮后由后端更新主题状态，"
                 "再通过 mutgui.reload() 让浏览器重连并重新安装对应扩展。"
             )},
            {"$component": "antd.Typography.Paragraph", "$id": "theme-status",
             "children": PerViewport(lambda vid: f"当前主题：{self.theme_mode}")},
            {"$component": "antd.Typography.Paragraph", "$id": "connection-id",
             "type": "secondary",
             "children": PerViewport(lambda vid: f"当前连接 channel_id：{vid}")},
            {"$component": "div", "$id": "actions",
             "style": {"display": "flex", "gap": 8, "flexWrap": "wrap", "marginBottom": 16},
             "$children": [
                 {"$component": "antd.Button", "$id": "use-none",
                  "children": "切到无主题", "onClick": Callback(self._use_none)},
                 {"$component": "antd.Button", "$id": "use-dark", "type": "primary",
                  "children": "切到黑色主题", "onClick": Callback(self._use_dark)},
             ]},
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "antd.Form.Item", "$id": "fi", "label": "Input",
                  "$children": [
                      {"$component": "antd.Input", "$id": "in",
                       "placeholder": "none/dark 切换后观察表单与按钮主题"},
                  ]},
             ]},
            {"$component": "antd.Button", "$id": "btn",
             "type": "primary",
             "children": f"Primary Button ({self.click_count})",
             "onClick": Callback(self._on_click)},
        ])


class ThemingRoute(MutguiRoute):
    view: ThemingDemoView

    def runtime_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for href in self._runtime_css:
            messages.append({"type": "runtime.css", "href": href})
        for name in self._runtime_imports:
            messages.append({"type": "runtime.import", "module": name})
        if self.view.theme_mode == "dark":
            messages.append({"type": "runtime.install", "module": "@mutgui/theme-dark"})
        messages.append({"type": "runtime.mount"})
        return messages


view = ThemingDemoView()
app = DemoApp([
    ThemingRoute("/", view, title="Theming", layout="plain", runtime_installs=()),
])


if __name__ == "__main__":
    app.run()
