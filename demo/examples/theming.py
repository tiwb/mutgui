"""自定义主题 demo — 演示如何写自己的 Plugin 实现主题定制。

mutgui 框架本身不认识"主题",只提供通用的 Plugin 协议:
  - ctx.addCss(css)         注入 CSS
  - ctx.addBodyClass(name)  加 body class
  - ctx.wrapRoot(wrap)      在 React 根外包一层(通常是 antd ConfigProvider)

本 demo 在 HTML 里内联写了一个 MyPurpleTheme plugin,做了三件事:
  1. 注入 CSS 覆盖 --mutgui-* token 为紫色系
  2. 加 body class .my-purple 激活覆盖
  3. 用 antd ConfigProvider 配紫色 token,让 antd 组件一起变紫

这就是内置 mutgui-theme-dark.js 的等价路径 —— 用户可以照此写任意主题。
"""
from __future__ import annotations

from mutgui import View, ViewBlock, Callback

from demo.framework import MutguiRoute, DemoApp


class ThemingDemoView(View):
    def __init__(self) -> None:
        self.click_count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Typography.Title", "$id": "title",
             "level": 3, "children": "Custom Theme Demo"},
            {"$component": "Typography.Paragraph", "$id": "desc",
             "children": (
                 "这个页面用的是自定义紫色 Plugin(不是内置的 mutgui-theme-dark)。 "
                 "Plugin 源码就写在页面 HTML 里,展示如何定制主题。"
             )},
            {"$component": "Typography.Title", "$id": "t2",
             "level": 5, "children": "antd 控件跟着主题走"},
            {"$component": "Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "Form.Item", "$id": "fi", "label": "Input",
                  "$children": [
                      {"$component": "Input", "$id": "in",
                       "placeholder": "主题色影响 focus / button"},
                  ]},
             ]},
            {"$component": "Button", "$id": "btn",
             "type": "primary",
             "children": f"Primary Button ({self.click_count})",
             "onClick": Callback(self._on_click)},
            {"$component": "Typography.Title", "$id": "t3",
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


# 自定义 HTML,内联写一个 MyPurpleTheme plugin
THEMING_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mutgui — Custom Theme</title>
</head>
<body>
  <div style="max-width: 720px; margin: 40px auto; font-family: sans-serif;">
    <div id="app"></div>
  </div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/mutgui-antd.js"></script>
  <script>
    // 一个自定义的紫色主题 Plugin
    // Plugin 签名: (ctx) => void,ctx 暴露 addCss / addBodyClass / wrapRoot 三个能力
    const MyPurpleTheme = (ctx) => {
      // 1. 注入 CSS — 覆盖 mutgui 的 --mutgui-* token 为紫色系
      ctx.addCss(`
        body.my-purple,
        body.my-purple .mutgui-root {
          color-scheme: dark;
          --mutgui-accent:    oklch(0.65 0.22 310);
          --mutgui-bg:        oklch(0.20 0.04 300);
          --mutgui-surface:   oklch(0.26 0.05 300);
          --mutgui-text:      oklch(0.92 0.02 310);
          --mutgui-text-dim:  oklch(0.70 0.04 310);
          --mutgui-border:    oklch(0.40 0.06 300);
        }
        body.my-purple {
          background: var(--mutgui-bg);
          color: var(--mutgui-text);
          min-height: 100vh;
          margin: 0;
        }
      `);

      // 2. 加 body class 激活上面的规则
      ctx.addBodyClass('my-purple');

      // 3. 用 antd ConfigProvider 配置 antd 的主题(紫色 + darkAlgorithm)
      const { antd, React } = MutguiApp;
      const antdTheme = {
        algorithm: antd.theme.darkAlgorithm,
        token: { colorPrimary: '#b07cff' },
      };
      ctx.wrapRoot((children) =>
        React.createElement(antd.ConfigProvider, { theme: antdTheme }, children)
      );
    };

    MutguiApp.mount(
      document.getElementById('app'),
      `ws://${location.host}${location.pathname}`,
      [MyPurpleTheme]
    );
  </script>
</body>
</html>
"""


app = DemoApp([
    MutguiRoute("/", ThemingDemoView(), title="Custom Theme", html=THEMING_HTML),
])


if __name__ == "__main__":
    app.run()
