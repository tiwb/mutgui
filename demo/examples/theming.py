"""自定义主题 demo — 演示后端安装一个自定义主题扩展实现主题定制。

mutgui 框架本身不认识"主题"，但后端可以在运行时要求前端安装一个扩展模块。
本 demo 使用 `@mutgui/theme-purple` 扩展模块，效果与之前内联脚本版等价：
  1. 注入 CSS 覆盖 --mutgui-* token 为紫色系
  2. 给 body 添加类名激活覆盖
  3. 用 antd ConfigProvider 配紫色 token，让 antd 组件一起变紫
"""
from __future__ import annotations

from mutgui import View, ViewBlock, Callback

from demo.framework import DemoApp, MutguiRoute


class ThemingDemoView(View):
    click_count: int = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "Custom Theme Demo"},
             {"$component": "antd.Typography.Paragraph", "$id": "desc",
              "children": (
                  "这个页面用的是自定义紫色主题扩展（不是内置的 mutgui-theme-dark）。 "
                  "页面 HTML 不再内联前端脚本，而是由后端在连接建立后下发安装该扩展的指令。"
              )},
            {"$component": "antd.Typography.Title", "$id": "t2",
             "level": 5, "children": "antd 控件跟着主题走"},
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "antd.Form.Item", "$id": "fi", "label": "Input",
                  "$children": [
                      {"$component": "antd.Input", "$id": "in",
                       "placeholder": "主题色影响 focus / button"},
                  ]},
             ]},
            {"$component": "antd.Button", "$id": "btn",
             "type": "primary",
             "children": f"Primary Button ({self.click_count})",
             "onClick": Callback(self._on_click)},
            {"$component": "antd.Typography.Title", "$id": "t3",
             "level": 5, "style": {"marginTop": 24},
             "children": "mutgui 组件也跟着 --mutgui-* token 走"},
            {"$component": "div", "$id": "surface-box",
             "style": {
                 "padding": 16, "marginTop": 8,
                 "background": "var(--mutgui-surface)",
                 "border": "1px solid var(--mutgui-border)",
                 "borderRadius": 4,
                 "color": "var(--mutgui-text)",
             },
             "children": "这是一个引用 --mutgui-surface / border / text token 的 div"},
        ])

    def _on_click(self) -> None:
        self.click_count += 1
        self.invalidate()

app = DemoApp([
    MutguiRoute(
        "/",
        ThemingDemoView(),
        title="Custom Theme",
        layout="plain",
        runtime_installs=("@mutgui/theme-purple",),
    ),
])


if __name__ == "__main__":
    app.run()
