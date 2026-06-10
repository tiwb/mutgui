"""Action System demo — category、widget、split、复杂 dropdown 与 DockPanel 集成。"""

from __future__ import annotations

from typing import Any

from mutgui import (
    Action,
    ActionCategoryProvider,
    ActionContext,
    ActionMenu,
    ActionRef,
    ActionToolbar,
    Callback,
    DockPanel,
    Expr,
    PanelDef,
    SplitNode,
    TabSetNode,
    View,
    ViewBlock,
    MenuTrigger,
)

from demo.framework import DemoApp, MutguiRoute


CONTROL_STYLE = {
    "height": "30px",
    "borderRadius": "6px",
    "border": "1px solid var(--mutgui-border)",
    "background": "var(--mutgui-bg)",
    "color": "var(--mutgui-text)",
}


class PanelView(View):
    title: str

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "div",
            "$id": "panel",
            "style": {
                "height": "100%",
                "padding": "16px",
                "boxSizing": "border-box",
            },
            "$children": [
                {"$component": "div", "$id": "title",
                 "style": {"fontWeight": "bold", "marginBottom": "8px"},
                 "children": self.title},
                {"$component": "div", "$id": "desc",
                 "style": {"color": "var(--mutgui-text-dim)"},
                 "children": "DockPanel 上方动作与这里的 tabset actions 使用同一套 Action 模型。"},
            ],
        }])


class ZoomWidget(View):
    page: "ActionDemoPage | None" = None

    def render(self) -> ViewBlock:
        value = "100%"
        if self.page is not None:
            value = self.page.zoom_value
        return ViewBlock([{
            "$component": "select",
            "$id": "zoom",
            "value": value,
            "style": dict(CONTROL_STYLE),
            "onChange": Callback(self._on_change, value=Expr.wire("$0.target.value")),
            "$children": [
                {"$component": "option", "$id": "z80", "value": "80%", "children": "80%"},
                {"$component": "option", "$id": "z100", "value": "100%", "children": "100%"},
                {"$component": "option", "$id": "z125", "value": "125%", "children": "125%"},
                {"$component": "option", "$id": "z150", "value": "150%", "children": "150%"},
            ],
        }])

    def _on_change(self, *, value: str) -> None:
        if self.page is None:
            return
        self.page.zoom_value = value
        self.invalidate()
        self.page.invalidate_action_views()
        self.page.log(f"缩放切换为 {value}")
        self.page.invalidate()


class DockStatusWidget(View):
    page: "ActionDemoPage | None" = None

    def render(self) -> ViewBlock:
        zoom = "100%"
        if self.page is not None:
            zoom = self.page.zoom_value
        return ViewBlock([{
            "$component": "span",
            "$id": "dock-status",
            "style": {"fontSize": "12px", "color": "var(--mutgui-text-dim)"},
            "children": f"缩放 {zoom}",
        }])


class GridConfigView(View):
    page: "ActionDemoPage | None" = None

    def render(self) -> ViewBlock:
        enabled = False
        density = 16
        if self.page is not None:
            enabled = self.page.grid_enabled
            density = self.page.grid_density
        return ViewBlock([{
            "$component": "div",
            "$id": "grid-config",
            "style": {
                "display": "flex",
                "flexDirection": "column",
                "gap": "10px",
                "padding": "10px",
                "minWidth": "220px",
                "background": "var(--mutgui-menu-bg, var(--mutgui-surface))",
                "color": "var(--mutgui-text)",
            },
            "$children": [
                {"$component": "div", "$id": "title",
                 "style": {"fontWeight": "bold"},
                 "children": "网格设置"},
                {"$component": "label", "$id": "toggle-wrap",
                 "style": {"display": "flex", "gap": "8px", "alignItems": "center"},
                 "$children": [
                     {"$component": "input", "$id": "toggle",
                      "type": "checkbox", "checked": enabled,
                      "style": {"accentColor": "var(--mutgui-accent)"},
                      "onChange": Callback(self._toggle_enabled,
                                           value=Expr.wire("$0.target.checked"))},
                     {"$component": "span", "$id": "toggle-label",
                      "children": "显示网格"},
                 ]},
                {"$component": "label", "$id": "density-wrap",
                 "style": {"display": "flex", "gap": "8px", "alignItems": "center"},
                 "$children": [
                     {"$component": "span", "$id": "density-label",
                      "children": "密度"},
                     {"$component": "input", "$id": "density",
                       "type": "range", "min": 8, "max": 64, "step": 8,
                       "value": density,
                       "style": {"accentColor": "var(--mutgui-accent)"},
                       "onChange": Callback(self._set_density,
                                            value=Expr.wire("$0.target.value"))},
                     {"$component": "span", "$id": "density-value",
                      "children": str(density)},
                 ]},
            ],
        }])

    def _toggle_enabled(self, *, value: bool) -> None:
        if self.page is None:
            return
        self.page.grid_enabled = value
        self.invalidate()
        self.page.invalidate_action_views()
        self.page.log(f"网格{'开启' if value else '关闭'}")
        self.page.invalidate()

    def _set_density(self, *, value: str) -> None:
        if self.page is None:
            return
        self.page.grid_density = int(value)
        self.invalidate()
        self.page.invalidate_action_views()
        self.page.log(f"网格密度切换为 {value}")
        self.page.invalidate()


class PaletteMenuView(View):
    page: "ActionDemoPage | None" = None

    def render(self) -> ViewBlock:
        keyword = ""
        if self.page is not None:
            keyword = self.page.palette_keyword
        swatches = ["#1677ff", "#722ed1", "#13c2c2", "#fa8c16", "#eb2f96"]
        return ViewBlock([{
            "$component": "div",
            "$id": "palette",
            "style": {
                "display": "flex",
                "flexDirection": "column",
                "gap": "10px",
                "padding": "10px",
                "minWidth": "240px",
                "background": "var(--mutgui-menu-bg, var(--mutgui-surface))",
                "color": "var(--mutgui-text)",
            },
            "$children": [
                {"$component": "div", "$id": "title",
                 "style": {"fontWeight": "bold"},
                 "children": "工具栏内嵌复杂菜单 UI"},
                {"$component": "input", "$id": "search",
                 "value": keyword, "placeholder": "筛选调色板",
                 "style": dict(CONTROL_STYLE),
                 "onChange": Callback(self._set_keyword, value=Expr.wire("$0.target.value"))},
                {"$component": "div", "$id": "swatches",
                 "style": {"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                 "$children": [
                     {"$component": "button", "$id": f"swatch-{index}",
                      "type": "button",
                      "style": {
                           "width": "28px",
                           "height": "28px",
                           "borderRadius": "6px",
                           "border": "1px solid var(--mutgui-border)",
                           "background": color,
                       },
                      "title": color,
                      "onClick": Callback(
                          lambda picked=color: self._pick_color(picked),
                      )}
                     for index, color in enumerate(swatches)
                 ]},
            ],
        }])

    def _set_keyword(self, *, value: str) -> None:
        if self.page is None:
            return
        self.page.palette_keyword = value
        self.page.invalidate()

    def _pick_color(self, color: str) -> None:
        if self.page is None:
            return
        self.page.log(f"选择颜色 {color}")


class SaveAction(Action):
    action_id = "demo.save"
    label = "保存"
    icon = "💾"
    tooltip = "保存当前工作区"
    shortcut = "Ctrl+S"
    categories = ("demo.toolbar.main", "demo.context.main", "demo.file.menu")
    position = "start"
    placement = "command:10/10"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("保存当前工作区")


class RunAction(Action):
    action_id = "demo.run"
    label = "运行"
    icon = "▶"
    tooltip = "运行当前命令"
    shortcut = "F5"
    categories = ("demo.toolbar.main", "demo.file.menu")
    position = "start"
    placement = "command:10/20"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("执行当前命令")


class CheckAction(Action):
    action_id = "demo.check"
    label = "检查"
    icon = "🧪"
    tooltip = "执行资源检查"
    shortcut = "Ctrl+Shift+K"
    categories = ("demo.toolbar.main", "demo.context.main")
    position = "start"
    placement = "pipeline:20/10"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("执行资源检查")


class PublishAction(Action):
    action_id = "demo.publish"
    label = "发布"
    icon = "🚀"
    tooltip = "发布当前版本"
    shortcut = "Ctrl+Shift+P"
    categories = ("demo.toolbar.main", "demo.file.menu")
    position = "start"
    placement = "pipeline:20/20"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("发布当前版本")


class SnapshotAction(Action):
    action_id = "demo.snapshot"
    label = "快照"
    icon = "📸"
    tooltip = "生成当前界面快照"
    shortcut = "Ctrl+Alt+S"
    categories = ("demo.toolbar.main",)
    position = "start"
    placement = "review:30/10"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("生成当前界面快照")


class OverviewAction(Action):
    action_id = "demo.overview"
    label = "概览"
    tooltip = "打开概览面板"
    shortcut = "Shift+1"
    categories = ("demo.toolbar.main",)
    position = "start"
    placement = "review:30/20"

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log("打开概览面板")


class ZoomAction(Action):
    action_id = "demo.zoom"
    label = "缩放"
    tooltip = "调整视图缩放"
    shortcut = "Ctrl+MouseWheel"
    categories = ("demo.toolbar.main", "demo.dock.actions")
    position = "end"
    placement = "view:30/30"

    def toolbar_view(self, context: ActionContext) -> View | None:
        return ZoomWidget(page=context.get("page"))

    def menu_view(self, context: ActionContext) -> View | None:
        return ZoomWidget(page=context.get("page"))


class DockStatusAction(Action):
    action_id = "demo.dock.status"
    label = "状态"
    categories = ("demo.dock.actions",)
    position = "end"
    placement = "meta:40/10"

    def toolbar_view(self, context: ActionContext) -> View | None:
        return DockStatusWidget(page=context.get("page"))


class GridAction(Action):
    action_id = "demo.grid"
    label = "网格"
    icon = "▦"
    tooltip = "切换网格与查看设置"
    shortcut = "Ctrl+'"
    categories = ("demo.toolbar.main", "demo.dock.actions")
    position = "end"
    placement = "view:30/20"

    def check_checked(self, context: ActionContext) -> bool:
        page = context.get("page")
        return bool(page.grid_enabled) if page is not None else False

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is None:
            return
        page.grid_enabled = not page.grid_enabled
        page.invalidate_action_views()
        page.log(f"主按钮切换网格为 {'开启' if page.grid_enabled else '关闭'}")
        page.invalidate()

    def menu_view(self, context: ActionContext) -> View | None:
        return GridConfigView(page=context.get("page"))


class PaletteAction(Action):
    action_id = "demo.palette"
    label = "调色板"
    icon = "🎛"
    tooltip = "打开调色板"
    shortcut = "Ctrl+Shift+C"
    categories = ("demo.toolbar.main",)
    position = "end"
    placement = "view:30/10"

    def menu_view(self, context: ActionContext) -> View | None:
        return PaletteMenuView(page=context.get("page"))


class RecentFileAction(Action):
    path: str = ""
    icon = "🕘"

    def resolved_label(self, context: "ActionContext | None" = None) -> str:
        return self.path

    def execute(self, context: ActionContext) -> None:
        page = context.get("page")
        if page is not None:
            page.log(f"打开最近文件：{self.path}")


class ContextMenuProvider(ActionCategoryProvider):
    categories = ("demo.context.main",)

    def refs(self, context: ActionContext) -> list[ActionRef]:
        return [
            ActionRef(action=RunAction),
            ActionRef(action=CheckAction),
            ActionRef(category="demo.recent.files"),
        ]


class RecentFilesProvider(ActionCategoryProvider):
    categories = ("demo.recent.files",)

    def refs(self, context: ActionContext) -> list[ActionRef]:
        page = context.get("page")
        if page is None:
            return []
        return [
            ActionRef(
                action=RecentFileAction(path=path),
                ref_id=f"recent-file-{index}",
                placement=f"recent:20/{index + 1}",
            )
            for index, path in enumerate(page.recent_files)
        ]


class ActionDemoPage(View):
    zoom_value: str = "100%"
    grid_enabled: bool = True
    grid_density: int = 24
    palette_keyword: str = ""
    logs: list[str]
    recent_files: list[str]
    toolbar: ActionToolbar
    compact_toolbar: ActionToolbar
    dock: DockPanel

    def __init__(self) -> None:
        super().__init__()
        self.logs = [
            "右键中央区域可打开 ActionMenu。",
            "Toolbar 左侧包含 command / pipeline / review 三组动作，可直接看到 separator。",
            "第二条 toolbar 使用 icon-only：有图标时只显示图标，无图标时仍显示文字。",
            "保存、运行等 action 现在带有 shortcut 元数据；menu 与 toolbar tip 都会展示。",
        ]
        self.recent_files = [
            "scene/main.scene",
            "prefabs/enemy_boss.prefab",
            "materials/water.mat",
        ]
        self.toolbar = ActionToolbar(
            id="main-toolbar",
            categories=["demo.toolbar.main"],
            context=self._action_context(),
        )
        self.compact_toolbar = ActionToolbar(
            id="compact-toolbar",
            categories=["demo.toolbar.main"],
            context=self._action_context(),
            label_mode="icon-only",
        )

        self.dock = DockPanel(
            id="dock",
            panels={
                "scene":     PanelDef("Scene",     icon="🗺",  view=PanelView("Scene")),
                "inspector": PanelDef("Inspector", icon="🧩", view=PanelView("Inspector")),
                "console":   PanelDef("Console",   icon="📜", view=PanelView("Console")),
            },
            layout=SplitNode(
                direction="horizontal",
                ratio=0.65,
                children=(
                    TabSetNode(
                        panel_ids=["scene", "console"],
                        active_id="scene",
                        actions=[
                            ActionRef(action=GridAction),
                            ActionRef(action=DockStatusAction),
                        ],
                    ),
                    TabSetNode(
                        panel_ids=["inspector"],
                        active_id="inspector",
                    ),
                ),
            ),
        )
        self.dock.action_context = ActionContext(data={"page": self})

    def render(self) -> ViewBlock:
        context = self._action_context()
        return ViewBlock([{
            "$component": "div",
            "$id": "page",
            "style": {
                "display": "flex",
                "flexDirection": "column",
                "gap": "16px",
                "padding": "16px",
                "height": "100%",
                "boxSizing": "border-box",
            },
            "$children": [
                {"$component": "div", "$id": "intro",
                 "$children": [
                     {"$component": "div", "$id": "title",
                      "style": {"fontSize": "20px", "fontWeight": "bold"},
                      "children": "Action System Demo"},
                     {"$component": "div", "$id": "desc",
                        "style": {"color": "#666"},
                        "children": "演示 toolbar separator 分组、toolbar 文本偏好、category 组合、toolbar widget、split button、复杂 dropdown UI 和 DockPanel richer actions。"},
                   ]},
                {"$component": "div", "$id": "toolbar-title-default",
                 "style": {"fontWeight": "bold"},
                 "children": "默认 toolbar（图标 + 文字）"},
                self.toolbar,
                {"$component": "div", "$id": "toolbar-title-compact",
                 "style": {"fontWeight": "bold", "marginTop": "4px"},
                 "children": "图标优先 toolbar（有图标时隐藏文字，无图标 action 仍显示文字）"},
                self.compact_toolbar,
                {"$component": "div", "$id": "actions-row",
                  "style": {"display": "flex", "gap": "12px", "alignItems": "center"},
                  "$children": [
                      {"$component": "button", "$id": "open-file-menu", "type": "button",
                       "children": "打开同组动作菜单",
                       "onClick": MenuTrigger(
                           lambda ctx=context:
                               ActionMenu(categories=["demo.toolbar.main"], context=ctx),
                           placement="bottom-start",
                       )},
                      {"$component": "div", "$id": "hint",
                        "style": {"color": "#666"},
                        "children": f"这个菜单与上方 toolbar 收集同一组 action，可直接对比同一动作在两种呈现下的效果；当前缩放 {self.zoom_value} / 网格密度 {self.grid_density}"},
                   ]},
                {"$component": "div", "$id": "context-target",
                 "style": {
                     "border": "1px dashed color-mix(in oklch, var(--mutgui-accent) 45%, var(--mutgui-border))",
                     "borderRadius": "8px",
                     "padding": "20px",
                     "background": "color-mix(in oklch, var(--mutgui-accent) 12%, var(--mutgui-surface))",
                     "color": "var(--mutgui-text)",
                 },
                 "children": "在这里右键，看看 category + provider 组合出来的 ActionMenu。",
                 "onContextMenu": MenuTrigger(
                     lambda ctx=context:
                         ActionMenu(categories=["demo.context.main"], context=ctx),
                     placement="cursor",
                 )},
                {"$component": "div", "$id": "dock-wrap",
                 "style": {"flex": 1, "minHeight": "280px"},
                 "$children": [self.dock]},
                {"$component": "div", "$id": "log-wrap",
                 "style": {
                     "borderTop": "1px solid #f0f0f0",
                     "paddingTop": "12px",
                     "display": "flex",
                     "flexDirection": "column",
                     "gap": "6px",
                 },
                 "$children": [
                     {"$component": "div", "$id": "log-title",
                      "style": {"fontWeight": "bold"},
                      "children": "事件日志"},
                     *[
                         {"$component": "div", "$id": f"log-{index}",
                          "style": {"fontFamily": "monospace"},
                          "children": line}
                         for index, line in enumerate(self.logs[-8:])
                     ],
                 ]},
            ],
        }])

    def log(self, message: str) -> None:
        self.logs.append(message)
        self.invalidate()

    def invalidate_action_views(self) -> None:
        self.toolbar.invalidate()
        self.compact_toolbar.invalidate()
        self.dock.invalidate()

    def _action_context(self) -> ActionContext:
        return ActionContext(
            surface="toolbar",
            data={"page": self},
        )


app = DemoApp([
    MutguiRoute("/", ActionDemoPage(), title="Action System", layout="plain"),
])

if __name__ == "__main__":
    app.run()
