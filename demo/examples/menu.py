"""菜单系统 demo — 右键菜单、placement、flip 与尺寸稳定性。"""
from __future__ import annotations

import mutobj

from mutgui import (
    View, ViewBlock, Callback, Bind, Expr,
    MenuView, MenuTrigger,
)

from demo.framework import DemoApp, MutguiRoute


SIDE_PLACEMENTS = [
    "top-start",
    "top-center",
    "top-end",
    "left-start",
    "left-end",
    "right-start",
    "right-end",
    "bottom-start",
    "bottom-center",
    "bottom-end",
]


# ---------------------------------------------------------------------------
# 各类菜单实现
# ---------------------------------------------------------------------------

class TabContextMenu(MenuView):
    """右键菜单 — 演示静态菜单 + disabled。"""

    item_id: str = "?"
    page: "MenuDemoPage | None" = None

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

    page: "MenuDemoPage | None" = None

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": "new-tab",
             "label": "New Tab", "icon": "+", "shortcut": "Ctrl+T",
             "onClick": Callback(self._on_new_tab)},
            {"$component": "mutgui.Menu.Item", "$id": "new-from",
             "label": "New from Template", "icon": "▣",
             "hasSubmenu": True, "closeOnClick": False,
             "onMouseEnter": MenuTrigger(
                 lambda: TemplateSubmenu(page=self.page),
                 placement="right-start",
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

    page: "MenuDemoPage | None" = None

    def render(self) -> ViewBlock:
        templates = ["Empty", "Python Script", "React App", "FastAPI Service"]
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": f"tpl-{t}",
             "label": t,
             "onClick": Callback(self._on_pick, t)}
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

    query: str = ""
    page: "MenuDemoPage | None" = None

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
                      "border": "1px solid var(--mutgui-border)",
                      "background": "var(--mutgui-bg)",
                      "color": "var(--mutgui-text)",
                      "borderRadius": "4px",
                      "fontSize": "13px", "outline": "none",
                  },
                  "onChange": Bind(self, "query", "$0.target.value")},
             ]},
            {"$component": "mutgui.Menu.Divider"},
        ]
        if not filtered:
            items.append({
                "$component": "div", "$id": "empty",
                "style": {"padding": "12px", "color": "var(--mutgui-text-dim)",
                          "fontSize": "12px", "textAlign": "center"},
                "children": "No commands match",
            })
        else:
            for cmd_id, label, shortcut in filtered[:8]:
                items.append({
                    "$component": "mutgui.Menu.Item",
                    "$id": cmd_id, "label": label, "shortcut": shortcut,
                    "onClick": Callback(self._on_pick, label),
                })
        return ViewBlock(items)

    def _on_pick(self, name: str) -> None:
        if self.page:
            self.page.log(f"Run: {name}")


class PlacementPreviewMenu(MenuView):
    """显示当前 placement 的简单菜单。"""

    placement_label: str = "cursor"
    page: "MenuDemoPage | None" = None

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "div", "$id": "meta",
             "style": {
                 "padding": "8px 10px",
                 "fontSize": "12px",
                 "color": "var(--mutgui-text-dim)",
             },
             "children": f"placement = {self.placement_label}"},
            {"$component": "mutgui.Menu.Divider"},
            {"$component": "mutgui.Menu.Item", "$id": "preview-open",
             "label": f"Open via {self.placement_label}",
             "onClick": Callback(self._on_pick)},
            {"$component": "mutgui.Menu.Item", "$id": "preview-align",
             "label": "Anchor follows the button corner"},
        ])

    def _on_pick(self) -> None:
        if self.page:
            self.page.log(f"Preview {self.placement_label}")


class EdgeFlipMenu(MenuView):
    """用于边缘 flip / size 演示的大菜单。"""

    title: str = "flip"
    page: "MenuDemoPage | None" = None

    def render(self) -> ViewBlock:
        items: list[dict] = [
            {"$component": "div", "$id": "title",
             "style": {
                 "padding": "8px 10px",
                 "fontSize": "12px",
                 "color": "var(--mutgui-text-dim)",
             },
             "children": f"Edge flip demo — {self.title}"},
            {"$component": "mutgui.Menu.Divider"},
        ]
        for index in range(1, 11):
            items.append({
                "$component": "mutgui.Menu.Item",
                "$id": f"edge-{index}",
                "label": f"Long menu item {index}",
                "shortcut": f"Alt+{index}",
                "onClick": Callback(self._on_pick, index),
            })
        return ViewBlock(items)

    def _on_pick(self, index: int) -> None:
        if self.page:
            self.page.log(f"Edge flip item {self.title}:{index}")


class ResizeStableMenu(MenuView):
    """演示菜单尺寸变化时锚点稳定。"""

    placement_label: str = "bottom-start"
    page: "MenuDemoPage | None" = None
    extra_count: int = 4

    def render(self) -> ViewBlock:
        items: list[dict] = [
            {"$component": "div", "$id": "header",
             "style": {
                 "padding": "8px 10px 4px 10px",
                 "fontSize": "12px",
                 "color": "var(--mutgui-text-dim)",
             },
             "children": f"Resize stability — {self.placement_label}"},
            {"$component": "div", "$id": "controls",
             "style": {
                 "display": "flex",
                 "gap": "8px",
                 "alignItems": "center",
                 "padding": "0 10px 8px 10px",
             },
             "$children": [
                 {"$component": "button", "$id": "dec",
                  "style": {
                      "width": "28px",
                      "height": "28px",
                      "border": "1px solid var(--mutgui-border)",
                      "background": "var(--mutgui-surface)",
                      "color": "var(--mutgui-text)",
                      "borderRadius": "4px",
                      "cursor": "pointer",
                  },
                  "children": "−",
                  "onClick": Callback(self._decrease)},
                 {"$component": "div", "$id": "count",
                  "style": {"minWidth": "96px", "fontSize": "12px"},
                  "children": f"{self.extra_count} dynamic items"},
                 {"$component": "button", "$id": "inc",
                  "style": {
                      "width": "28px",
                      "height": "28px",
                      "border": "1px solid var(--mutgui-border)",
                      "background": "var(--mutgui-surface)",
                      "color": "var(--mutgui-text)",
                      "borderRadius": "4px",
                      "cursor": "pointer",
                  },
                  "children": "+",
                  "onClick": Callback(self._increase)},
             ]},
            {"$component": "mutgui.Menu.Divider"},
        ]
        for index in range(self.extra_count):
            items.append({
                "$component": "mutgui.Menu.Item",
                "$id": f"dyn-{index}",
                "label": f"Dynamic item {index + 1}",
                "onClick": Callback(self._on_pick, index + 1),
            })
        return ViewBlock(items)

    def _increase(self) -> None:
        self.extra_count += 1
        self.invalidate()

    def _decrease(self) -> None:
        if self.extra_count > 1:
            self.extra_count -= 1
            self.invalidate()

    def _on_pick(self, index: int) -> None:
        if self.page:
            self.page.log(f"Resize stability {self.placement_label}:{index}")


# ---------------------------------------------------------------------------
# Demo 页面
# ---------------------------------------------------------------------------

class MenuDemoPage(View):
    log_lines: list[str] = mutobj.field(default_factory=list)

    def log(self, msg: str) -> None:
        self.log_lines.append(msg)
        self.log_lines = self.log_lines[-12:]
        self.invalidate()

    def render(self) -> ViewBlock:
        placement_buttons = [
            {"$component": "button", "$id": f"placement-{placement}",
             "onClick": MenuTrigger(
                 lambda placement=placement: PlacementPreviewMenu(
                     placement_label=placement,
                     page=self,
                 ),
                 placement=placement,
             ),
             "style": {
                 "padding": "8px 10px",
                 "border": "1px solid var(--mutgui-border)",
                 "background": "var(--mutgui-surface)",
                 "color": "var(--mutgui-text)",
                 "borderRadius": "4px",
                 "cursor": "pointer",
                 "fontSize": "12px",
             },
             "children": placement}
            for placement in SIDE_PLACEMENTS
        ]
        resize_buttons = [
            {"$component": "button", "$id": f"stable-{placement}",
             "onClick": MenuTrigger(
                 lambda placement=placement: ResizeStableMenu(
                     placement_label=placement,
                     page=self,
                 ),
                 placement=placement,
             ),
             "style": {
                 "padding": "8px 10px",
                 "border": "1px solid var(--mutgui-border)",
                 "background": "var(--mutgui-surface)",
                 "color": "var(--mutgui-text)",
                 "borderRadius": "4px",
                 "cursor": "pointer",
                 "fontSize": "12px",
             },
             "children": placement}
            for placement in SIDE_PLACEMENTS
        ]
        return ViewBlock([{
            "$component": "div", "$id": "wrap",
            "style": {"padding": "24px", "fontFamily": "system-ui", "margin": "0 auto"},
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
                               lambda item_id: TabContextMenu(item_id=item_id, page=self),
                               item_id=Expr.wire("$0.currentTarget.dataset.id"),
                           ),
                           "style": {
                               "padding": "8px 16px",
                               "border": "1px solid var(--mutgui-border)",
                               "borderRadius": "4px", "cursor": "context-menu",
                               "background": "var(--mutgui-surface)",
                               "color": "var(--mutgui-text)",
                               "userSelect": "none",
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
                           lambda: AddDropdownMenu(page=self),
                           placement="bottom-start",
                       ),
                       "style": {
                           "padding": "8px 16px", "marginTop": "8px",
                           "border": "1px solid var(--mutgui-accent)",
                           "background": "var(--mutgui-accent)",
                          "color": "var(--mutgui-text)",
                          "borderRadius": "4px", "cursor": "pointer",
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
                           lambda: CommandPalette(page=self),
                           placement="bottom-start",
                       ),
                       "style": {
                           "padding": "8px 16px", "marginTop": "8px",
                           "border": "1px solid var(--mutgui-border)",
                           "background": "var(--mutgui-surface)",
                          "color": "var(--mutgui-text)",
                          "borderRadius": "4px", "cursor": "pointer",
                       },
                       "children": "⌘ Open Palette"},
                  ]},

                 # placement 矩阵
                 {"$component": "div", "$id": "placement-section",
                  "style": {"marginTop": "24px"},
                  "$children": [
                      {"$component": "h4", "$id": "placement-h",
                       "children": "Placement matrix"},
                      {"$component": "div", "$id": "placement-help",
                       "style": {
                           "marginTop": "8px",
                           "fontSize": "12px",
                           "color": "var(--mutgui-text-dim)",
                       },
                       "children": "Right-click list covers cursor; buttons below cover the 10 side-align placements."},
                      {"$component": "div", "$id": "placement-grid",
                       "style": {
                           "display": "grid",
                           "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                           "gap": "8px",
                           "marginTop": "10px",
                       },
                       "$children": placement_buttons},
                  ]},

                 # 边缘 flip 演示
                 {"$component": "div", "$id": "flip-section",
                  "style": {"marginTop": "24px"},
                  "$children": [
                      {"$component": "h4", "$id": "flip-h",
                       "children": "Edge flip"},
                      {"$component": "div", "$id": "flip-box",
                       "style": {
                           "position": "relative",
                           "height": "240px",
                           "marginTop": "8px",
                           "border": "1px dashed var(--mutgui-border)",
                           "borderRadius": "8px",
                           "background": "var(--mutgui-surface)",
                       },
                       "$children": [
                           {"$component": "button", "$id": "flip-left-top",
                            "onClick": MenuTrigger(
                                lambda: EdgeFlipMenu(title="left-start", page=self),
                                placement="left-start",
                            ),
                            "style": {
                                "position": "absolute",
                                "left": "12px",
                                "top": "12px",
                                "padding": "8px 10px",
                                "border": "1px solid var(--mutgui-border)",
                                "background": "var(--mutgui-bg)",
                                "color": "var(--mutgui-text)",
                                "borderRadius": "4px",
                                "cursor": "pointer",
                            },
                            "children": "left-start @ top-left"},
                           {"$component": "button", "$id": "flip-right-top",
                            "onClick": MenuTrigger(
                                lambda: EdgeFlipMenu(title="top-end", page=self),
                                placement="top-end",
                            ),
                            "style": {
                                "position": "absolute",
                                "right": "12px",
                                "top": "12px",
                                "padding": "8px 10px",
                                "border": "1px solid var(--mutgui-border)",
                                "background": "var(--mutgui-bg)",
                                "color": "var(--mutgui-text)",
                                "borderRadius": "4px",
                                "cursor": "pointer",
                            },
                            "children": "top-end @ top-right"},
                           {"$component": "button", "$id": "flip-left-bottom",
                            "onClick": MenuTrigger(
                                lambda: EdgeFlipMenu(title="bottom-start", page=self),
                                placement="bottom-start",
                            ),
                            "style": {
                                "position": "absolute",
                                "left": "12px",
                                "bottom": "12px",
                                "padding": "8px 10px",
                                "border": "1px solid var(--mutgui-border)",
                                "background": "var(--mutgui-bg)",
                                "color": "var(--mutgui-text)",
                                "borderRadius": "4px",
                                "cursor": "pointer",
                            },
                            "children": "bottom-start @ bottom-left"},
                           {"$component": "button", "$id": "flip-right-bottom",
                            "onClick": MenuTrigger(
                                lambda: EdgeFlipMenu(title="right-end", page=self),
                                placement="right-end",
                            ),
                            "style": {
                                "position": "absolute",
                                "right": "12px",
                                "bottom": "12px",
                                "padding": "8px 10px",
                                "border": "1px solid var(--mutgui-border)",
                                "background": "var(--mutgui-bg)",
                                "color": "var(--mutgui-text)",
                                "borderRadius": "4px",
                                "cursor": "pointer",
                            },
                            "children": "right-end @ bottom-right"},
                       ]},
                  ]},

                 # 尺寸稳定性演示
                 {"$component": "div", "$id": "stable-section",
                  "style": {"marginTop": "24px"},
                  "$children": [
                      {"$component": "h4", "$id": "stable-h",
                       "children": "Resize stability"},
                      {"$component": "div", "$id": "stable-help",
                       "style": {
                           "marginTop": "8px",
                           "fontSize": "12px",
                           "color": "var(--mutgui-text-dim)",
                       },
                       "children": "Open any placement, then use +/- inside the menu to change item count and watch the anchored corner stay fixed."},
                      {"$component": "div", "$id": "stable-grid",
                       "style": {
                           "display": "grid",
                           "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                           "gap": "8px",
                           "marginTop": "10px",
                       },
                       "$children": resize_buttons},
                  ]},

                 # 操作日志
                 {"$component": "div", "$id": "log-section",
                  "style": {"marginTop": "24px"},
                  "$children": [
                     {"$component": "h4", "$id": "log-h",
                      "children": "Action log"},
                     {"$component": "pre", "$id": "log",
                      "style": {
                          "padding": "12px",
                          "background": "var(--mutgui-surface)",
                          "color": "var(--mutgui-text)",
                          "border": "1px solid var(--mutgui-border)",
                          "borderRadius": "4px", "minHeight": "120px",
                          "fontSize": "12px", "fontFamily": "monospace",
                          "marginTop": "8px",
                      },
                      "children": "\n".join(self.log_lines) or "(no actions yet)"},
                 ]},
            ],
        }])

app = DemoApp([
    MutguiRoute("/", MenuDemoPage(), title="Menu System", layout="plain"),
])

if __name__ == "__main__":
    app.run()
