"""Action system 单元测试。"""

from mutgui import (
    Action,
    ActionCategoryProvider,
    ActionContext,
    ActionMenu,
    ActionRef,
    ActionToolbar,
    DockPanel,
    PanelDef,
    SplitNode,
    TabSetNode,
    View,
    ViewBlock,
)
from mutgui._action_registry import (
    _action_classes,
    _provider_classes,
    resolve_actions,
)
from mutgui._dock_panel_impl import _dp_ext


class StaticAction(Action):
    action_id = "test.static"
    label = "静态动作"
    categories = ("test.action.main",)
    position = "start"
    placement = "base:10/10"

    def execute(self, context: ActionContext) -> None:
        pass


class RecentAction(Action):
    name: str = ""

    def resolved_label(self, context: ActionContext | None = None) -> str:
        return f"最近：{self.name}"

    def execute(self, context: ActionContext) -> None:
        pass


class RecentProvider(ActionCategoryProvider):
    categories = ("test.action.main",)

    def refs(self, context: ActionContext) -> list[ActionRef]:
        return [
            ActionRef(
                action=RecentAction(name=name),
                ref_id=f"recent-{index}",
                placement=f"recent:20/{index + 1}",
            )
            for index, name in enumerate(context.get("recent", []))
        ]


class LookupOrderAction(Action):
    action_id = "test.lookup-order"
    label = "排序查找"
    order = 7

    def __post_init__(self) -> None:
        raise RuntimeError("排序不应实例化 action")


class LookupOrderProvider(ActionCategoryProvider):
    categories = ("test.lookup.provider",)
    order = 3

    def __post_init__(self) -> None:
        raise RuntimeError("排序不应实例化 provider")


class ToolbarWidget(View):
    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "span",
            "$id": "widget",
            "children": "widget",
        }])


class MarkerView(View):
    marker: str = ""

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "span",
            "$id": "marker",
            "children": self.marker,
        }])


class WidgetAction(Action):
    action_id = "test.widget"
    label = "部件"

    def toolbar_view(self, context: ActionContext) -> View | None:
        return ToolbarWidget()


class SplitMenuView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "div",
            "$id": "menu-root",
            "children": "menu",
        }])


class SplitAction(Action):
    action_id = "test.split"
    label = "拆分"
    icon = "S"

    def execute(self, context: ActionContext) -> None:
        pass

    def menu_view(self, context: ActionContext) -> View | None:
        return SplitMenuView()


class MenuOnlyAction(Action):
    action_id = "test.menu-only"
    label = "仅菜单"

    def menu_view(self, context: ActionContext) -> View | None:
        return SplitMenuView()


class ContextProbeAction(Action):
    action_id = "test.context-probe"
    label = "探针"

    def execute(self, context: ActionContext) -> None:
        pass

    def toolbar_view(self, context: ActionContext) -> View | None:
        marker = context.get("marker", "missing")
        return MarkerView(marker=marker)


def test_action_registry_category_and_provider() -> None:
    resolved = resolve_actions(
        context=ActionContext(data={"recent": ["scene", "material"]}),
        categories=["test.action.main"],
    )

    assert [item.label for item in resolved] == [
        "静态动作",
        "最近：scene",
        "最近：material",
    ]
    assert resolved[0].position == "start"


def test_action_toolbar_builds_start_and_end_groups() -> None:
    toolbar = ActionToolbar(
        id="toolbar",
        refs=[
            ActionRef(action=StaticAction),
            ActionRef(action=WidgetAction),
            ActionRef(action=SplitAction),
        ],
    )

    block = toolbar.render()
    root = block.items[0]
    assert root["$id"] == "toolbar"
    groups = root["$children"]
    assert groups[0]["$id"] == "start"
    assert groups[2]["$id"] == "end"
    assert groups[0]["$children"][0]["$id"] == "button-0"
    assert groups[2]["$children"][0]["$id"] == "widget-1"
    assert groups[2]["$children"][1]["$id"] == "split-2"


def test_action_toolbar_renders_dropdown_with_arrow() -> None:
    toolbar = ActionToolbar(
        id="toolbar",
        refs=[ActionRef(action=MenuOnlyAction, placement="10")],
    )

    block = toolbar.render()
    dropdown = block.items[0]["$children"][2]["$children"][0]
    assert dropdown["$id"] == "dropdown-0"
    assert dropdown["$children"][-1]["$id"] == "arrow"
    assert dropdown["$children"][-1]["children"] == "▾"


def test_action_registry_class_level_defaults_do_not_instantiate_for_lookup() -> None:
    action_classes = _action_classes()
    provider_classes = _provider_classes()

    assert LookupOrderAction in action_classes
    assert LookupOrderProvider in provider_classes


class PlacementDefaultAction(Action):
    action_id = "test.placement.default"
    label = "默认"
    position = "start"

    def execute(self, context: ActionContext) -> None:
        pass


class PlacementAlphaAction(Action):
    action_id = "test.placement.alpha"
    label = "Alpha"
    position = "start"
    placement = "alpha:10/2"

    def execute(self, context: ActionContext) -> None:
        pass


class PlacementAlphaFirstAction(Action):
    action_id = "test.placement.alpha-first"
    label = "AlphaFirst"
    position = "start"
    placement = "alpha:10/1"

    def execute(self, context: ActionContext) -> None:
        pass


class PlacementBetaAction(Action):
    action_id = "test.placement.beta"
    label = "Beta"
    position = "start"
    placement = "beta:20/1:-2"

    def execute(self, context: ActionContext) -> None:
        pass


class PlacementLegacyOrderAction(Action):
    action_id = "test.placement.legacy"
    label = "Legacy"
    position = "start"
    order = 5

    def execute(self, context: ActionContext) -> None:
        pass


class IconLabelAction(Action):
    action_id = "test.icon-label"
    label = "图文"
    icon = "I"
    tooltip = "图文提示"
    shortcut = "Ctrl+I"
    position = "start"

    def execute(self, context: ActionContext) -> None:
        pass


class LabelOnlyAction(Action):
    action_id = "test.label-only"
    label = "纯文字"
    position = "start"

    def execute(self, context: ActionContext) -> None:
        pass


class InlineMenuWidgetAction(Action):
    action_id = "test.inline-menu-widget"
    label = "内联"
    position = "start"

    def toolbar_view(self, context: ActionContext) -> View | None:
        return ToolbarWidget()

    def menu_view(self, context: ActionContext) -> View | None:
        return MarkerView(marker="inline-menu")


class DuplicateStaticAction(Action):
    action_id = "test.duplicate.static"
    label = "重复"
    categories = ("test.duplicate.main",)
    position = "start"

    def execute(self, context: ActionContext) -> None:
        pass


class DuplicateProvider(ActionCategoryProvider):
    categories = ("test.duplicate.main",)

    def refs(self, context: ActionContext) -> list[ActionRef]:
        return [ActionRef(action=DuplicateStaticAction)]


def test_dockpanel_action_wire_supports_nested_handlers_and_widget_children() -> None:
    dock = DockPanel(
        id="dock",
        panels=[PanelDef("a", "A"), PanelDef("b", "B")],
        layout=SplitNode(
            direction="horizontal",
            children=(
                TabSetNode(
                    panel_ids=["a"],
                    active_id="a",
                    actions=[
                        ActionRef(action=SplitAction),
                        ActionRef(action=WidgetAction),
                    ],
                ),
                TabSetNode(panel_ids=["b"], active_id="b"),
            ),
        ),
    )
    dock.set_panel_view("a", ToolbarWidget())
    dock.set_panel_view("b", ToolbarWidget())
    _dp_ext(dock).viewport_sizes[1] = (800, 600)

    result = dock.render_viewport([{"$component": "mutgui.DockPanel", "$id": "dock"}], 1)
    split = result[0]["$children"][0]
    tabset = split["$children"][0]
    actions = tabset["actions"]

    assert actions[0]["variant"] == "split"
    assert actions[0]["onMenuClick"]["menu"] is True
    assert actions[1]["variant"] == "widget"
    assert actions[1]["$children"][0]["$component"] == "span"


def test_dockpanel_action_context_data_is_merged() -> None:
    dock = DockPanel(
        id="dock",
        panels=[PanelDef("a", "A")],
        layout=TabSetNode(
            panel_ids=["a"],
            active_id="a",
            actions=[ActionRef(action=ContextProbeAction)],
        ),
    )
    _dp_ext(dock).action_context_data["marker"] = "from-dock"
    dock.set_panel_view("a", ToolbarWidget())
    _dp_ext(dock).viewport_sizes[1] = (800, 600)

    result = dock.render_viewport([{"$component": "mutgui.DockPanel", "$id": "dock"}], 1)
    tabset = result[0]["$children"][0]
    actions = tabset["actions"]
    assert actions[0]["variant"] == "widget"
    assert actions[0]["$children"][0]["children"] == "from-dock"


def test_action_registry_sorts_by_placement_tokens() -> None:
    resolved = resolve_actions(
        context=ActionContext(),
        refs=[
            ActionRef(action=PlacementBetaAction),
            ActionRef(action=PlacementAlphaAction),
            ActionRef(action=PlacementDefaultAction, placement="10"),
            ActionRef(action=PlacementAlphaFirstAction),
            ActionRef(action=PlacementLegacyOrderAction),
        ],
    )

    assert [item.label for item in resolved] == [
        "Legacy",
        "默认",
        "AlphaFirst",
        "Alpha",
        "Beta",
    ]
    assert [item.group_name for item in resolved] == [
        "",
        "",
        "alpha",
        "alpha",
        "beta",
    ]


def test_action_menu_inserts_divider_when_group_changes() -> None:
    menu = ActionMenu(
        refs=[
            ActionRef(action=PlacementDefaultAction, placement="10"),
            ActionRef(action=PlacementAlphaFirstAction),
            ActionRef(action=PlacementAlphaAction),
            ActionRef(action=PlacementBetaAction),
        ],
    )

    block = menu.render()
    assert [item["$component"] for item in block.items] == [
        "mutgui.Menu.Item",
        "mutgui.Menu.Divider",
        "mutgui.Menu.Item",
        "mutgui.Menu.Item",
        "mutgui.Menu.Divider",
        "mutgui.Menu.Item",
    ]


def test_action_menu_uses_submenu_for_toolbar_dropdown_like_actions() -> None:
    menu = ActionMenu(refs=[ActionRef(action=SplitAction, placement="10")])

    block = menu.render()
    item = block.items[0]
    assert item["$component"] == "mutgui.Menu.Item"
    assert item["hasSubmenu"] is True


def test_action_registry_marks_menu_only_action_as_dropdown() -> None:
    resolved = resolve_actions(
        context=ActionContext(surface="toolbar"),
        refs=[ActionRef(action=MenuOnlyAction, placement="10")],
    )

    assert resolved[0].variant == "dropdown"
    assert resolved[0].can_execute is False


def test_action_menu_keeps_widget_style_actions_inline() -> None:
    menu = ActionMenu(refs=[ActionRef(action=InlineMenuWidgetAction, placement="10")])

    block = menu.render()
    assert isinstance(block.items[0], View)
    assert block.items[0].id.endswith("menu-view-test.inline-menu-widget-0")


def test_action_toolbar_inserts_separator_when_group_changes() -> None:
    toolbar = ActionToolbar(
        id="placement-toolbar",
        refs=[
            ActionRef(action=PlacementDefaultAction, placement="10"),
            ActionRef(action=PlacementAlphaFirstAction),
            ActionRef(action=PlacementAlphaAction),
            ActionRef(action=PlacementBetaAction),
        ],
    )

    block = toolbar.render()
    start_children = block.items[0]["$children"][0]["$children"]
    assert [item["$id"] for item in start_children] == [
        "button-0",
        "divider-1",
        "button-1",
        "button-2",
        "divider-3",
        "button-3",
    ]


def test_action_toolbar_icon_only_hides_text_when_icon_exists() -> None:
    toolbar = ActionToolbar(
        id="icon-only-toolbar",
        label_mode="icon-only",
        refs=[
            ActionRef(action=IconLabelAction, placement="10"),
            ActionRef(action=LabelOnlyAction, placement="20"),
        ],
    )

    block = toolbar.render()
    start_children = block.items[0]["$children"][0]["$children"]
    assert start_children[0]["children"] == "I"
    assert start_children[1]["children"] == "纯文字"


def test_action_toolbar_default_label_mode_keeps_icon_and_text() -> None:
    toolbar = ActionToolbar(
        id="default-toolbar",
        refs=[ActionRef(action=IconLabelAction, placement="10")],
    )

    block = toolbar.render()
    start_children = block.items[0]["$children"][0]["$children"]
    assert [child["children"] for child in start_children[0]["$children"]] == ["I", "图文"]
    assert start_children[0]["title"] == "图文提示 (Ctrl+I)"


def test_dockpanel_action_wire_carries_group_name() -> None:
    dock = DockPanel(
        id="dock",
        panels=[PanelDef("a", "A")],
        layout=TabSetNode(
            panel_ids=["a"],
            active_id="a",
            actions=[
                ActionRef(action=PlacementAlphaAction),
                ActionRef(action=PlacementBetaAction),
            ],
        ),
    )
    dock.set_panel_view("a", ToolbarWidget())
    _dp_ext(dock).viewport_sizes[1] = (800, 600)

    result = dock.render_viewport([{"$component": "mutgui.DockPanel", "$id": "dock"}], 1)
    tabset = result[0]["$children"][0]
    actions = tabset["actions"]
    assert [action["groupName"] for action in actions] == ["alpha", "beta"]


def test_action_registry_dedupes_same_action_from_category_and_provider() -> None:
    resolved = resolve_actions(
        context=ActionContext(),
        categories=["test.duplicate.main"],
    )

    labels = [item.label for item in resolved]
    assert labels.count("重复") == 1
