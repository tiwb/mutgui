"""No-theme demo — 演示不安装任何主题扩展时的框架默认行为。

mutgui 框架本身不提供主题。base.css 的 token 默认值为亮色,
对齐浏览器默认、antd / MUI / Chakra 等主流组件库默认。

这个 demo:
  - 后端不下发任何主题安装消息
  - antd 无 ConfigProvider → 默认亮色 (antd 自带的 light 主题)
  - mutgui 的 --mutgui-* token 用 base.css 的亮色默认值
  - body 无特殊 class,浏览器默认白底黑字

效果:纯亮色页面,和 antd 官网 demo 一致的视觉。
这就是"mutgui 不做主题"时的真实样貌,也是给消费者看的底色。
"""
from __future__ import annotations

from mutgui import View, ViewBlock, Callback

from demo.framework import DemoApp, MutguiRoute


class NoThemeView(View):
    click_count: int = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "No Theme — mutgui 零预设"},
            {"$component": "antd.Typography.Paragraph", "$id": "desc",
             "children": (
                 "此页面不安装任何主题扩展。后端只下发基础 CSS 和组件库导入, "
                 "mutgui 框架不认识'主题',token 默认为亮色, "
                 "antd 无 ConfigProvider 也默认亮色,两者自然一致。"
              )},
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "antd.Form.Item", "$id": "fi", "label": "Input",
                  "$children": [
                      {"$component": "antd.Input", "$id": "in",
                       "placeholder": "antd 默认亮色"},
                  ]},
             ]},
            {"$component": "antd.Button", "$id": "btn",
             "type": "primary",
             "children": f"Primary Button ({self.click_count})",
             "onClick": Callback(self._on_click)},
            {"$component": "antd.Typography.Paragraph", "$id": "hint",
             "type": "secondary",
             "style": {"marginTop": 24, "fontSize": 13},
              "children": (
                  "对比 /theming/ 可以看到相同业务代码在不同运行时扩展下的效果。"
              )},
        ])

    def _on_click(self) -> None:
        self.click_count += 1
        self.invalidate()

app = DemoApp([
    MutguiRoute("/", NoThemeView(), title="No Theme", layout="plain", runtime_installs=()),
])


if __name__ == "__main__":
    app.run()
