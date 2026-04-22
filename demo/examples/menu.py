"""菜单系统 demo — 右键菜单、下拉菜单、子菜单、带搜索的菜单。"""
from __future__ import annotations

from mutgui import (
    View, ViewBlock, Callback, Bind,
    MenuView, MenuTrigger,
)

from demo.framework import MutguiRoute, DemoApp


# ---------------------------------------------------------------------------
# 各类菜单实现
# ---------------------------------------------------------------------------

class TabContextMenu(MenuView):
    """右键菜单 — 演示静态菜单 + disabled。"""

    def __init__(self, item_id: str = "?", page: "MenuDemoPage | None" = None) -> None:
        super().__init__()
        self.item_id = item_id
        self.page = page

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": "rename",
             "label": f"Rename {self.item_id}", "icon": "✏",
             "shortcut": "F2",
             "onClick": Callback(self._on_rename)},
            {"$component": "mutgui.Menu.Item", "$id": "dup",
             "label": "Duplicate", "icon": "❑"},
            {"$component": "mutgui.Menu.Divider"},
            {"$component": "mutgui.Menu.Item", "$id": "del",
             "label": f"Delete {self.item_id}", "icon": "🗑",
             "shortcut": "Del",
             "onClick": Callback(self._on_delete)},
            {"$component": "mutgui.Menu.Item", "$id": "props",
             "label": "Properties", "disabled": True,
             "shortcut": "Alt+Enter"},
        ])

    def _on_rename(self) -> None:
        if self.page:
            self.page.log(f"Rename {self.item_id}")

    def _on_delete(self) -> None:
        if self.page:
            self.page.log(f"Delete {self.item_id}")


class AddDropdownMenu(MenuView):
    """下拉菜单 + 子菜单触发。"""

    def __init__(self, page: "MenuDemoPage | None" = None) -> None:
        super().__init__()
        self.page = page

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": "new-tab",
             "label": "New Tab", "icon": "+", "shortcut": "Ctrl+T",
             "onClick": Callback(self._on_new_tab)},
            {"$component": "mutgui.Menu.Item", "$id": "new-from",
             "label": "New from Template", "icon": "▣",
             "hasSubmenu": True, "closeOnClick": False,
             "onMouseEnter": MenuTrigger(
                 lambda: TemplateSubmenu(self.page),
                 placement="right",
             )},
            {"$component": "mutgui.Menu.Divider"},
            {"$component": "mutgui.Menu.Item", "$id": "import",
             "label": "Import...", "icon": "⇣",
             "onClick": Callback(self._on_import)},
        ])

    def _on_new_tab(self) -> None:
        if self.page:
            self.page.log("New Tab")

    def _on_import(self) -> None:
        if self.page:
            self.page.log("Import")


class TemplateSubmenu(MenuView):
    """子菜单。"""

    def __init__(self, page: "MenuDemoPage | None" = None) -> None:
        super().__init__()
        self.page = page

    def render(self) -> ViewBlock:
        templates = ["Empty", "Python Script", "React App", "FastAPI Service"]
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": f"tpl-{t}",
             "label": t,
             "onClick": Callback(lambda name=t: self._on_pick(name))}
            for t in templates
        ])

    def _on_pick(self, name: str) -> None:
        if self.page:
            self.page.log(f"New from template: {name}")


class CommandPalette(MenuView):
    """带搜索的菜单 — 演示菜单内放任意组件 + 持续交互。"""

    ALL_COMMANDS = [
        ("file.new", "File: New", "Ctrl+N"),
        ("file.open", "File: Open...", "Ctrl+O"),
        ("file.save", "File: Save", "Ctrl+S"),
        ("file.close", "File: Close", "Ctrl+W"),
        ("edit.copy", "Edit: Copy", "Ctrl+C"),
        ("edit.paste", "Edit: Paste", "Ctrl+V"),
        ("edit.find", "Edit: Find", "Ctrl+F"),
        ("view.zoom-in", "View: Zoom In", "Ctrl++"),
        ("view.zoom-out", "View: Zoom Out", "Ctrl+-"),
        ("term.toggle", "Terminal: Toggle", "Ctrl+`"),
    ]

    def __init__(self, page: "MenuDemoPage | None" = None) -> None:
        super().__init__()
        self.query = ""
        self.page = page

    def render(self) -> ViewBlock:
        q = self.query.lower()
        filtered = [c for c in self.ALL_COMMANDS if q in c[1].lower()]
        items: list = [
            {"$component": "div", "$id": "search-wrap",
             "style": {"padding": "6px"},
             "$children": [
                 {"$component": "input", "$id": "search",
                  "type": "text", "placeholder": "Search commands...",
                  "value": self.query,
                  "autoFocus": True,
                  "style": {
                      "width": "100%", "padding": "6px 8px",
                      "border": "1px solid #ddd", "borderRadius": "4px",
                      "fontSize": "13px", "outline": "none",
                  },
                  "onChange": Bind(self, "query", "$0.target.value")},
             ]},
            {"$component": "mutgui.Menu.Divider"},
        ]
        if not filtered:
            items.append({
                "$component": "div", "$id": "empty",
                "style": {"padding": "12px", "color": "#999",
                          "fontSize": "12px", "textAlign": "center"},
                "children": "No commands match",
            })
        else:
            for cmd_id, label, shortcut in filtered[:8]:
                items.append({
                    "$component": "mutgui.Menu.Item",
                    "$id": cmd_id, "label": label, "shortcut": shortcut,
                    "onClick": Callback(lambda name=label: self._on_pick(name)),
                })
        return ViewBlock(items)

    def _on_pick(self, name: str) -> None:
        if self.page:
            self.page.log(f"Run: {name}")


# ---------------------------------------------------------------------------
# Demo 页面
# ---------------------------------------------------------------------------

class MenuDemoPage(View):
    def __init__(self) -> None:
        self.log_lines: list[str] = []

    def log(self, msg: str) -> None:
        self.log_lines.append(msg)
        self.log_lines = self.log_lines[-12:]
        self.invalidate()

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "div", "$id": "wrap",
            "style": {"padding": "24px", "fontFamily": "system-ui",
                      "maxWidth": "900px", "margin": "0 auto"},
            "$children": [
                {"$component": "h2", "$id": "h", "children": "Menu System Demo"},

                # 右键菜单（多个 item）
                {"$component": "div", "$id": "ctx-section",
                 "style": {"marginTop": "16px"},
                 "$children": [
                     {"$component": "h4", "$id": "ctx-h",
                      "children": "Right-click menu (different per item)"},
                     {"$component": "div", "$id": "ctx-list",
                      "style": {
                          "display": "flex", "gap": "8px", "flexWrap": "wrap",
                          "marginTop": "8px",
                      },
                      "$children": [
                          {"$component": "div", "$id": f"item-{n}",
                           "data-id": f"tab-{n}",
                           "onContextMenu": MenuTrigger(
                               lambda item_id: TabContextMenu(item_id, self),
                               item_id="$0.currentTarget.dataset.id",
                           ),
                           "style": {
                               "padding": "8px 16px", "border": "1px solid #ccc",
                               "borderRadius": "4px", "cursor": "context-menu",
                               "background": "#f7f7f7", "userSelect": "none",
                           },
                           "children": f"Tab {n} (right-click)"}
                          for n in range(1, 6)
                      ]},
                 ]},

                # 下拉菜单 + 子菜单
                {"$component": "div", "$id": "dd-section",
                 "style": {"marginTop": "24px"},
                 "$children": [
                     {"$component": "h4", "$id": "dd-h",
                      "children": "Dropdown menu (with submenu)"},
                     {"$component": "button", "$id": "add-btn",
                      "onClick": MenuTrigger(
                          lambda: AddDropdownMenu(self),
                          placement="bottom",
                      ),
                      "style": {
                          "padding": "8px 16px", "marginTop": "8px",
                          "border": "1px solid #1677ff", "background": "#1677ff",
                          "color": "white", "borderRadius": "4px", "cursor": "pointer",
                      },
                      "children": "+ Add"},
                 ]},

                # 命令面板
                {"$component": "div", "$id": "cmd-section",
                 "style": {"marginTop": "24px"},
                 "$children": [
                     {"$component": "h4", "$id": "cmd-h",
                      "children": "Searchable menu (Command Palette)"},
                     {"$component": "button", "$id": "cmd-btn",
                      "onClick": MenuTrigger(
                          lambda: CommandPalette(self),
                          placement="bottom",
                      ),
                      "style": {
                          "padding": "8px 16px", "marginTop": "8px",
                          "border": "1px solid #999", "background": "white",
                          "borderRadius": "4px", "cursor": "pointer",
                      },
                      "children": "⌘ Open Palette"},
                 ]},

                # 操作日志
                {"$component": "div", "$id": "log-section",
                 "style": {"marginTop": "24px"},
                 "$children": [
                     {"$component": "h4", "$id": "log-h",
                      "children": "Action log"},
                     {"$component": "pre", "$id": "log",
                      "style": {
                          "padding": "12px", "background": "#1e1e1e", "color": "#d4d4d4",
                          "borderRadius": "4px", "minHeight": "120px",
                          "fontSize": "12px", "fontFamily": "monospace",
                          "marginTop": "8px",
                      },
                      "children": "\n".join(self.log_lines) or "(no actions yet)"},
                 ]},
            ],
        }])


MENU_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mutgui — Menu System</title>
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #fafafa; }
    h2 { margin: 0 0 8px 0; }
    h4 { margin: 0; font-size: 13px; color: #666; }
  </style>
</head>
<body>
  <div id="app"></div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/libs/antd.js"></script>
  <script>MutguiApp.mount(document.getElementById('app'), `ws://${location.host}${location.pathname}`)</script>
</body>
</html>
"""


app = DemoApp([
    MutguiRoute("/", MenuDemoPage(), title="Menu System", html=MENU_HTML),
])

if __name__ == "__main__":
    app.run()
