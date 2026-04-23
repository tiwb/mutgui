"""DockPanel per-viewport 单元测试。"""

from typing import Any

from mutgui import View, ViewBlock, ViewPort, Channel
from mutgui.dock_panel import (
    DockPanel, PanelDef, SplitNode, TabSetNode,
)


class MockChannel(Channel):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def messages_for(self, view_id: list[str | int]) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("viewId") == view_id]


class PanelView(View):
    def __init__(self, label: str) -> None:
        self.label = label

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "Text", "$id": "t", "text": self.label,
        }])


def _make_dock(collapse_below: int = 600) -> DockPanel:
    """创建标准测试布局: 水平分割，左(A,B) 右(C)，坍缩阈值 600px。"""
    layout = SplitNode(
        direction="horizontal",
        children=(
            TabSetNode(panel_ids=["a", "b"], active_id="a"),
            TabSetNode(panel_ids=["c"], active_id="c"),
        ),
        collapse_below=collapse_below,
    )
    panels = [
        PanelDef(id="a", title="Panel A"),
        PanelDef(id="b", title="Panel B"),
        PanelDef(id="c", title="Panel C"),
    ]
    dock = DockPanel(id="dock", panels=panels, layout=layout)
    for pid in ["a", "b", "c"]:
        dock.set_panel_view(pid, PanelView(pid))
    return dock


# ---------------------------------------------------------------------------
# _compute_layout per-viewport
# ---------------------------------------------------------------------------

def test_compute_layout_no_collapse() -> None:
    """宽屏不坍缩。"""
    dock = _make_dock()
    result = dock._compute_layout(dock.layout, 800, 600)
    assert isinstance(result, SplitNode)


def test_compute_layout_collapsed() -> None:
    """窄屏坍缩为单个 TabSetNode。"""
    dock = _make_dock()
    collapsed_ids: set[str] = set()
    result = dock._compute_layout(dock.layout, 400, 600,
                                  collapsed_ids=collapsed_ids)
    assert isinstance(result, TabSetNode)
    assert set(result.panel_ids) == {"a", "b", "c"}
    assert len(collapsed_ids) == 1


def test_compute_layout_per_viewport_active() -> None:
    """不同 viewport 的 collapsed active 独立。"""
    dock = _make_dock()
    dock.viewport_collapsed_active[1] = {dock.layout.id or "": "b"}
    dock.viewport_collapsed_active[2] = {dock.layout.id or "": "c"}

    r1 = dock._compute_layout(dock.layout, 400, 600, channel_id=1)
    r2 = dock._compute_layout(dock.layout, 400, 600, channel_id=2)

    assert isinstance(r1, TabSetNode) and r1.active_id == "b"
    assert isinstance(r2, TabSetNode) and r2.active_id == "c"


def test_compute_layout_per_viewport_orders() -> None:
    """不同 viewport 的 collapsed tab 顺序独立。"""
    dock = _make_dock()
    split_id = dock.layout.id or ""
    dock.viewport_collapsed_orders[1] = {split_id: ["c", "b", "a"]}

    r1 = dock._compute_layout(dock.layout, 400, 600, channel_id=1)
    r2 = dock._compute_layout(dock.layout, 400, 600, channel_id=2)

    assert isinstance(r1, TabSetNode) and r1.panel_ids == ["c", "b", "a"]
    assert isinstance(r2, TabSetNode) and r2.panel_ids == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# render 模板模式
# ---------------------------------------------------------------------------

def test_render_template_includes_all_views() -> None:
    """render 输出所有面板 View 作为 children。"""
    dock = _make_dock()
    block = dock.render()
    children = block.items[0]["$children"]
    child_ids = {v.id for v in children}
    assert child_ids == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# transform
# ---------------------------------------------------------------------------

def test_transform_no_size_passthrough() -> None:
    """viewport 未报告尺寸时，transform 透传模板树。"""
    dock = _make_dock()
    template = [{"$component": "test", "$children": []}]
    result = dock.render_viewport(template, channel_id=99)
    assert result is template


def test_transform_wide_viewport() -> None:
    """宽屏 viewport 不坍缩 → transform 输出 Split 结构。"""
    dock = _make_dock()
    dock.viewport_sizes[1] = (800, 600)
    template = [{"$component": "mutgui.DockPanel", "$id": "dock"}]
    result = dock.render_viewport(template, channel_id=1)
    inner = result[0]["$children"][0]
    assert inner["$component"] == "mutgui.DockPanel.Split"


def test_transform_narrow_viewport() -> None:
    """窄屏 viewport 坍缩 → transform 输出 TabSet + collapsed 标记。"""
    dock = _make_dock()
    dock.viewport_sizes[1] = (400, 600)
    template = [{"$component": "mutgui.DockPanel", "$id": "dock"}]
    result = dock.render_viewport(template, channel_id=1)
    inner = result[0]["$children"][0]
    assert inner["$component"] == "mutgui.DockPanel.TabSet"
    assert inner["collapsed"] is True


def test_transform_two_viewports_independent() -> None:
    """两个 viewport 不同尺寸 → 各自独立的树结构。"""
    dock = _make_dock()
    dock.viewport_sizes[1] = (800, 600)  # 宽屏
    dock.viewport_sizes[2] = (400, 600)  # 窄屏
    template = [{"$component": "mutgui.DockPanel", "$id": "dock"}]

    r1 = dock.render_viewport(template, channel_id=1)
    r2 = dock.render_viewport(template, channel_id=2)

    assert r1[0]["$children"][0]["$component"] == "mutgui.DockPanel.Split"
    assert r2[0]["$children"][0]["$component"] == "mutgui.DockPanel.TabSet"


def test_transform_view_refs() -> None:
    """transform 输出的 wire tree 包含 $view 引用。"""
    dock = _make_dock()
    dock.viewport_sizes[1] = (800, 600)
    template = [{"$component": "mutgui.DockPanel", "$id": "dock"}]
    result = dock.render_viewport(template, channel_id=1)

    # Split 下有两个 TabSet，各有一个 $view child
    split = result[0]["$children"][0]
    left_tabset = split["$children"][0]
    right_tabset = split["$children"][1]
    assert left_tabset["$children"] == [{"$view": "a"}]
    assert right_tabset["$children"] == [{"$view": "c"}]


# ---------------------------------------------------------------------------
# 事件处理器
# ---------------------------------------------------------------------------

def test_on_resize_per_viewport() -> None:
    """resize 事件更新对应 viewport 的尺寸。"""
    dock = _make_dock()
    dock._on_resize(width=800, height=600, viewport_id=1)
    dock._on_resize(width=400, height=300, viewport_id=2)
    assert dock.viewport_sizes[1] == (800, 600)
    assert dock.viewport_sizes[2] == (400, 300)


def test_tab_switch_shared() -> None:
    """非坍缩态 tab_switch 修改共享 active_id。"""
    dock = _make_dock()
    left = dock.layout.children[0]  # type: ignore[union-attr]
    assert isinstance(left, TabSetNode)
    assert left.active_id == "a"

    dock._on_tab_switch(tabsetId=left.id or "", panelId="b", viewport_id=1)
    assert left.active_id == "b"


def test_tab_switch_collapsed_per_viewport() -> None:
    """坍缩态 tab_switch 只更新该 viewport 的 collapsed_active。"""
    dock = _make_dock()
    split_id = dock.layout.id or ""

    dock._on_tab_switch(tabsetId=split_id, panelId="b", viewport_id=1)
    dock._on_tab_switch(tabsetId=split_id, panelId="c", viewport_id=2)

    assert dock.viewport_collapsed_active[1][split_id] == "b"
    assert dock.viewport_collapsed_active[2][split_id] == "c"


def test_tab_reorder_collapsed_per_viewport() -> None:
    """坍缩态 tab_reorder 只更新该 viewport 的 collapsed_orders。"""
    dock = _make_dock()
    split_id = dock.layout.id or ""

    dock._on_tab_reorder(tabsetId=split_id,
                         panelIds=["c", "b", "a"], viewport_id=1)
    dock._on_tab_reorder(tabsetId=split_id,
                         panelIds=["b", "a", "c"], viewport_id=2)

    assert dock.viewport_collapsed_orders[1][split_id] == ["c", "b", "a"]
    assert dock.viewport_collapsed_orders[2][split_id] == ["b", "a", "c"]


# ---------------------------------------------------------------------------
# 端到端：两个 viewport 推送
# ---------------------------------------------------------------------------

async def test_end_to_end_two_viewports() -> None:
    """两个 viewport 各自收到独立的坍缩/非坍缩 wire tree。"""
    dock = _make_dock()

    class RootView(View):
        def render(self) -> ViewBlock:
            return ViewBlock([dock])

    root = RootView()
    ch1 = MockChannel()
    ch2 = MockChannel()

    vp1 = ViewPort(root, ch1)
    await vp1.initialize()
    await root.rendered()

    vp2 = ViewPort(root, ch2)
    await vp2.initialize()
    await root.rendered()

    # VP1: 宽屏 resize
    ch1.messages.clear()
    ch2.messages.clear()
    await vp1.handle_event({
        "source": ["dock", "dock"],
        "event": "onResize",
        "data": {"width": 800, "height": 600},
    })
    await root.rendered()
    await dock.rendered()

    dock_msgs_1 = ch1.messages_for(["dock"])
    assert len(dock_msgs_1) >= 1
    tree1 = dock_msgs_1[-1]["tree"]
    assert tree1[0]["$children"][0]["$component"] == "mutgui.DockPanel.Split"

    # VP2: 窄屏 resize
    ch1.messages.clear()
    ch2.messages.clear()
    await vp2.handle_event({
        "source": ["dock", "dock"],
        "event": "onResize",
        "data": {"width": 400, "height": 600},
    })
    await root.rendered()
    await dock.rendered()

    dock_msgs_2 = ch2.messages_for(["dock"])
    assert len(dock_msgs_2) >= 1
    tree2 = dock_msgs_2[-1]["tree"]
    assert tree2[0]["$children"][0]["$component"] == "mutgui.DockPanel.TabSet"
    assert tree2[0]["$children"][0].get("collapsed") is True

    # VP1 仍然是 Split（re-render 后未改变其状态）
    dock_msgs_1_after = ch1.messages_for(["dock"])
    if dock_msgs_1_after:
        tree1_after = dock_msgs_1_after[-1]["tree"]
        assert tree1_after[0]["$children"][0]["$component"] == "mutgui.DockPanel.Split"
