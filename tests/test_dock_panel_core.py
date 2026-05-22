"""DockPanel 核心逻辑单元测试——布局树操作、事件处理器、merge_bars。"""

from mutgui.dock_panel import (
    DockPanel, PanelDef, SplitNode, TabSetNode,
)
from mutgui._dock_panel_impl import (
    collect_all_panels, find_node, find_parent_split,
    find_active_in_subtree, set_active_in_subtree,
    replace_node, remove_panel_from_subtree, cleanup_tree,
    _dock_panel_on_tab_move, _dock_panel_on_split_resize,
    _dock_panel_on_tab_dock, _dock_panel_on_edge_dock,
    _dock_panel_build_split_component,
)


def _tree() -> SplitNode:
    """标准测试树:

    split-root (horizontal)
    ├── tabset-L [a, b] active=a
    └── split-R (vertical)
        ├── tabset-RT [c] active=c
        └── tabset-RB [d, e] active=d
    """
    return SplitNode(
        direction="horizontal",
        id="split-root",
        children=(
            TabSetNode(panel_ids=["a", "b"], id="tabset-L", active_id="a"),
            SplitNode(
                direction="vertical",
                id="split-R",
                children=(
                    TabSetNode(panel_ids=["c"], id="tabset-RT", active_id="c"),
                    TabSetNode(panel_ids=["d", "e"], id="tabset-RB",
                               active_id="d"),
                ),
            ),
        ),
    )


def _make_dock(layout: SplitNode | None = None) -> DockPanel:
    panels = {c: PanelDef(c.upper()) for c in "abcde"}
    return DockPanel(id="dock", panels=panels,
                     layout=layout or _tree())


# ---------------------------------------------------------------------------
# collect_all_panels
# ---------------------------------------------------------------------------

def test_collect_single_tabset() -> None:
    node = TabSetNode(panel_ids=["x", "y"])
    assert collect_all_panels(node) == ["x", "y"]


def test_collect_split() -> None:
    tree = _tree()
    assert set(collect_all_panels(tree)) == {"a", "b", "c", "d", "e"}


def test_collect_preserves_order() -> None:
    tree = _tree()
    result = collect_all_panels(tree)
    assert result == ["a", "b", "c", "d", "e"]


# ---------------------------------------------------------------------------
# find_node
# ---------------------------------------------------------------------------

def test_find_root() -> None:
    tree = _tree()
    assert find_node(tree, "split-root") is tree


def test_find_leaf_tabset() -> None:
    tree = _tree()
    node = find_node(tree, "tabset-RB")
    assert isinstance(node, TabSetNode)
    assert node.panel_ids == ["d", "e"]


def test_find_nested_split() -> None:
    tree = _tree()
    node = find_node(tree, "split-R")
    assert isinstance(node, SplitNode)
    assert node.direction == "vertical"


def test_find_not_found() -> None:
    tree = _tree()
    assert find_node(tree, "nonexistent") is None


# ---------------------------------------------------------------------------
# find_parent_split
# ---------------------------------------------------------------------------

def test_find_parent_direct_child() -> None:
    tree = _tree()
    parent = find_parent_split(tree, "tabset-L")
    assert parent is tree


def test_find_parent_nested() -> None:
    tree = _tree()
    parent = find_parent_split(tree, "tabset-RT")
    assert parent is not None
    assert parent.id == "split-R"


def test_find_parent_of_split_child() -> None:
    tree = _tree()
    parent = find_parent_split(tree, "split-R")
    assert parent is tree


def test_find_parent_root_returns_none() -> None:
    tree = _tree()
    assert find_parent_split(tree, "split-root") is None


def test_find_parent_not_found() -> None:
    tree = _tree()
    assert find_parent_split(tree, "nonexistent") is None


# ---------------------------------------------------------------------------
# find_active_in_subtree
# ---------------------------------------------------------------------------

def test_find_active_tabset() -> None:
    node = TabSetNode(panel_ids=["x", "y"], active_id="y")
    assert find_active_in_subtree(node) == "y"


def test_find_active_none() -> None:
    node = TabSetNode(panel_ids=[], active_id=None)
    assert find_active_in_subtree(node) is None


def test_find_active_nested() -> None:
    tree = _tree()
    assert find_active_in_subtree(tree) == "a"


# ---------------------------------------------------------------------------
# set_active_in_subtree
# ---------------------------------------------------------------------------

def test_set_active_found() -> None:
    tree = _tree()
    assert set_active_in_subtree(tree, "b") is True
    left = tree.children[0]
    assert isinstance(left, TabSetNode)
    assert left.active_id == "b"


def test_set_active_not_found() -> None:
    tree = _tree()
    assert set_active_in_subtree(tree, "z") is False


def test_set_active_nested() -> None:
    tree = _tree()
    assert set_active_in_subtree(tree, "e") is True
    rb = find_node(tree, "tabset-RB")
    assert isinstance(rb, TabSetNode)
    assert rb.active_id == "e"


# ---------------------------------------------------------------------------
# replace_node
# ---------------------------------------------------------------------------

def test_replace_root() -> None:
    tree = _tree()
    new = TabSetNode(panel_ids=["x"], id="new")
    result = replace_node(tree, "split-root", new)
    assert result is new


def test_replace_child() -> None:
    tree = _tree()
    new = TabSetNode(panel_ids=["x"], id="new")
    result = replace_node(tree, "tabset-L", new)
    assert isinstance(result, SplitNode)
    assert result.children[0] is new
    assert result is not tree


def test_replace_not_found_identity() -> None:
    tree = _tree()
    result = replace_node(tree, "nonexistent", TabSetNode(panel_ids=[]))
    assert result is tree


# ---------------------------------------------------------------------------
# remove_panel_from_subtree
# ---------------------------------------------------------------------------

def test_remove_panel_non_active() -> None:
    tree = _tree()
    assert remove_panel_from_subtree(tree, "b") is True
    left = tree.children[0]
    assert isinstance(left, TabSetNode)
    assert left.panel_ids == ["a"]
    assert left.active_id == "a"


def test_remove_panel_active_fallback() -> None:
    tree = _tree()
    assert remove_panel_from_subtree(tree, "a") is True
    left = tree.children[0]
    assert isinstance(left, TabSetNode)
    assert left.active_id == "b"


def test_remove_panel_last() -> None:
    tree = _tree()
    remove_panel_from_subtree(tree, "c")
    rt = find_node(tree, "tabset-RT")
    assert isinstance(rt, TabSetNode)
    assert rt.panel_ids == []
    assert rt.active_id is None


def test_remove_panel_not_found() -> None:
    tree = _tree()
    assert remove_panel_from_subtree(tree, "z") is False


def test_remove_panel_nested() -> None:
    tree = _tree()
    assert remove_panel_from_subtree(tree, "d") is True
    rb = find_node(tree, "tabset-RB")
    assert isinstance(rb, TabSetNode)
    assert rb.panel_ids == ["e"]
    assert rb.active_id == "e"


# ---------------------------------------------------------------------------
# cleanup_tree
# ---------------------------------------------------------------------------

def test_cleanup_tabset_passthrough() -> None:
    node = TabSetNode(panel_ids=["a"], id="ts")
    assert cleanup_tree(node) is node


def test_cleanup_empty_left() -> None:
    tree = SplitNode(
        direction="horizontal", id="s",
        children=(
            TabSetNode(panel_ids=[], id="empty"),
            TabSetNode(panel_ids=["a"], id="keep"),
        ),
    )
    result = cleanup_tree(tree)
    assert isinstance(result, TabSetNode)
    assert result.id == "keep"


def test_cleanup_empty_right() -> None:
    tree = SplitNode(
        direction="horizontal", id="s",
        children=(
            TabSetNode(panel_ids=["a"], id="keep"),
            TabSetNode(panel_ids=[], id="empty"),
        ),
    )
    result = cleanup_tree(tree)
    assert isinstance(result, TabSetNode)
    assert result.id == "keep"


def test_cleanup_merge_bars_correction() -> None:
    """merge_bars=True 但子节点不都是 TabSet → 修正为 False。"""
    inner_split = SplitNode(
        direction="vertical", id="inner",
        children=(
            TabSetNode(panel_ids=["a"], id="ts1"),
            TabSetNode(panel_ids=["b"], id="ts2"),
        ),
    )
    tree = SplitNode(
        direction="horizontal", id="outer",
        merge_bars=True,
        children=(
            inner_split,
            TabSetNode(panel_ids=["c"], id="ts3"),
        ),
    )
    result = cleanup_tree(tree)
    assert isinstance(result, SplitNode)
    assert result.merge_bars is False


def test_cleanup_merge_bars_preserved() -> None:
    """merge_bars=True 且两子节点都是 TabSet → 保持。"""
    tree = SplitNode(
        direction="horizontal", id="s",
        merge_bars=True,
        children=(
            TabSetNode(panel_ids=["a"], id="ts1"),
            TabSetNode(panel_ids=["b"], id="ts2"),
        ),
    )
    result = cleanup_tree(tree)
    assert result is tree
    assert isinstance(result, SplitNode)
    assert result.merge_bars is True


def test_cleanup_no_change_identity() -> None:
    tree = _tree()
    result = cleanup_tree(tree)
    assert result is tree


def test_cleanup_nested_empty() -> None:
    """嵌套的空 TabSet 被递归清理。"""
    tree = SplitNode(
        direction="horizontal", id="outer",
        children=(
            TabSetNode(panel_ids=["a"], id="keep"),
            SplitNode(
                direction="vertical", id="inner",
                children=(
                    TabSetNode(panel_ids=[], id="empty"),
                    TabSetNode(panel_ids=["b"], id="survivor"),
                ),
            ),
        ),
    )
    result = cleanup_tree(tree)
    assert isinstance(result, SplitNode)
    assert result.id == "outer"
    assert isinstance(result.children[1], TabSetNode)
    assert result.children[1].id == "survivor"


# ---------------------------------------------------------------------------
# _on_tab_move
# ---------------------------------------------------------------------------

def _make_simple_dock() -> DockPanel:
    """简单两面板: tabset-L [a, b], tabset-R [c]。"""
    layout = SplitNode(
        direction="horizontal",
        children=(
            TabSetNode(panel_ids=["a", "b"], active_id="a"),
            TabSetNode(panel_ids=["c"], active_id="c"),
        ),
    )
    return DockPanel(
        id="dock",
        panels={c: PanelDef(c.upper()) for c in "abc"},
        layout=layout,
    )


def test_tab_move_basic() -> None:
    dock = _make_simple_dock()
    left_id = dock.layout.children[0].id  # type: ignore[union-attr]
    right_id = dock.layout.children[1].id  # type: ignore[union-attr]
    _dock_panel_on_tab_move(dock, fromTabset=left_id or "", toTabset=right_id or "",
                      panelId="b", index=0)
    right = find_node(dock.layout, right_id or "")
    assert isinstance(right, TabSetNode)
    assert right.panel_ids == ["b", "c"]


def test_tab_move_source_emptied_cleanup() -> None:
    """移走最后一个 panel → 源 TabSet 被 cleanup 清除。"""
    layout = SplitNode(
        direction="horizontal",
        children=(
            TabSetNode(panel_ids=["a"]),
            TabSetNode(panel_ids=["b"]),
        ),
    )
    dock = DockPanel(
        id="dock",
        panels={"a": PanelDef("A"), "b": PanelDef("B")},
        layout=layout,
    )
    left_id = dock.layout.children[0].id  # type: ignore[union-attr]
    right_id = dock.layout.children[1].id  # type: ignore[union-attr]
    _dock_panel_on_tab_move(dock, fromTabset=left_id or "", toTabset=right_id or "",
                      panelId="a", index=1)
    assert isinstance(dock.layout, TabSetNode)
    assert dock.layout.panel_ids == ["b", "a"]


def test_tab_move_index_clamp() -> None:
    dock = _make_simple_dock()
    left_id = dock.layout.children[0].id  # type: ignore[union-attr]
    right_id = dock.layout.children[1].id  # type: ignore[union-attr]
    _dock_panel_on_tab_move(dock, fromTabset=left_id or "", toTabset=right_id or "",
                      panelId="a", index=999)
    right = find_node(dock.layout, right_id or "")
    assert isinstance(right, TabSetNode)
    assert right.panel_ids == ["c", "a"]


# ---------------------------------------------------------------------------
# _on_split_resize
# ---------------------------------------------------------------------------

def test_split_resize_normal() -> None:
    dock = _make_simple_dock()
    split_id = dock.layout.id or ""
    _dock_panel_on_split_resize(dock, splitId=split_id, ratio=0.3)
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.ratio == 0.3


def test_split_resize_clamp_high() -> None:
    dock = _make_simple_dock()
    split_id = dock.layout.id or ""
    _dock_panel_on_split_resize(dock, splitId=split_id, ratio=1.5)
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.ratio == 1.0


def test_split_resize_clamp_low() -> None:
    dock = _make_simple_dock()
    split_id = dock.layout.id or ""
    _dock_panel_on_split_resize(dock, splitId=split_id, ratio=-0.2)
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.ratio == 0.0


# ---------------------------------------------------------------------------
# _on_tab_dock
# ---------------------------------------------------------------------------

def test_tab_dock_right() -> None:
    dock = _make_dock()
    _dock_panel_on_tab_dock(dock, fromTabset="tabset-L", panelId="b",
                      targetTabset="tabset-RT", position="right")
    left = find_node(dock.layout, "tabset-L")
    assert isinstance(left, TabSetNode)
    assert "b" not in left.panel_ids
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_tab_dock_left() -> None:
    dock = _make_dock()
    _dock_panel_on_tab_dock(dock, fromTabset="tabset-RB", panelId="d",
                      targetTabset="tabset-L", position="left")
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_tab_dock_top() -> None:
    dock = _make_dock()
    _dock_panel_on_tab_dock(dock, fromTabset="tabset-L", panelId="a",
                      targetTabset="tabset-RB", position="top")
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_tab_dock_bottom() -> None:
    dock = _make_dock()
    _dock_panel_on_tab_dock(dock, fromTabset="tabset-RT", panelId="c",
                      targetTabset="tabset-L", position="bottom")
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_tab_dock_creates_new_split() -> None:
    """dock 到 right → 目标节点被包裹在新 SplitNode(horizontal) 内。"""
    dock = _make_dock()
    _dock_panel_on_tab_dock(dock, fromTabset="tabset-L", panelId="a",
                      targetTabset="tabset-RT", position="right")
    all_panels = collect_all_panels(dock.layout)
    assert "a" in all_panels
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_tab_dock_source_emptied() -> None:
    """dock 走源 TabSet 最后一个 panel → cleanup 清除空节点。"""
    layout = SplitNode(
        direction="horizontal",
        children=(
            TabSetNode(panel_ids=["a"]),
            TabSetNode(panel_ids=["b"]),
        ),
    )
    dock = DockPanel(
        id="dock",
        panels={"a": PanelDef("A"), "b": PanelDef("B")},
        layout=layout,
    )
    src_id = dock.layout.children[0].id  # type: ignore[union-attr]
    dst_id = dock.layout.children[1].id  # type: ignore[union-attr]
    _dock_panel_on_tab_dock(dock, fromTabset=src_id or "", panelId="a",
                      targetTabset=dst_id or "", position="right")
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b"}


# ---------------------------------------------------------------------------
# _on_edge_dock
# ---------------------------------------------------------------------------

def test_edge_dock_right() -> None:
    dock = _make_dock()
    _dock_panel_on_edge_dock(dock, fromTabset="tabset-L", panelId="a", edge="right")
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.direction == "horizontal"
    all_panels = collect_all_panels(dock.layout)
    assert set(all_panels) == {"a", "b", "c", "d", "e"}


def test_edge_dock_left() -> None:
    dock = _make_dock()
    _dock_panel_on_edge_dock(dock, fromTabset="tabset-RB", panelId="e", edge="left")
    assert isinstance(dock.layout, SplitNode)
    left = dock.layout.children[0]
    assert isinstance(left, TabSetNode)
    assert left.panel_ids == ["e"]


def test_edge_dock_top() -> None:
    dock = _make_dock()
    _dock_panel_on_edge_dock(dock, fromTabset="tabset-L", panelId="b", edge="top")
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.direction == "vertical"
    top = dock.layout.children[0]
    assert isinstance(top, TabSetNode)
    assert top.panel_ids == ["b"]


def test_edge_dock_bottom() -> None:
    dock = _make_dock()
    _dock_panel_on_edge_dock(dock, fromTabset="tabset-RT", panelId="c", edge="bottom")
    assert isinstance(dock.layout, SplitNode)
    assert dock.layout.direction == "vertical"
    bottom = dock.layout.children[1]
    assert isinstance(bottom, TabSetNode)
    assert bottom.panel_ids == ["c"]


def test_edge_dock_replaces_root() -> None:
    """edge dock 总是生成新的根 SplitNode。"""
    dock = _make_dock()
    old_root_id = dock.layout.id
    _dock_panel_on_edge_dock(dock, fromTabset="tabset-L", panelId="a", edge="right")
    assert dock.layout.id != old_root_id


# ---------------------------------------------------------------------------
# merge_bars 渲染
# ---------------------------------------------------------------------------

def test_build_split_wire_merge_bars() -> None:
    """merge_bars=True + 两 TabSet → mergedTabs + hideBar。"""
    layout = SplitNode(
        direction="horizontal",
        merge_bars=True,
        children=(
            TabSetNode(panel_ids=["a", "b"], active_id="a"),
            TabSetNode(panel_ids=["c"], active_id="c"),
        ),
    )
    dock = DockPanel(
        id="dock",
        panels={c: PanelDef(c.upper()) for c in "abc"},
        layout=layout,
    )
    wire = _dock_panel_build_split_component(dock, dock.layout, set())  # type: ignore[arg-type]
    assert "mergedTabs" in wire
    merged = wire["mergedTabs"]
    assert len(merged["left"]) == 2
    assert len(merged["right"]) == 1
    assert merged["leftActiveId"] == "a"
    assert merged["rightActiveId"] == "c"
    left_wire = wire["$children"][0]
    right_wire = wire["$children"][1]
    assert left_wire["hideBar"] is True
    assert right_wire["hideBar"] is True


def test_build_split_wire_no_merge_bars() -> None:
    """merge_bars=False → 无 mergedTabs。"""
    layout = SplitNode(
        direction="horizontal",
        merge_bars=False,
        children=(
            TabSetNode(panel_ids=["a"], active_id="a"),
            TabSetNode(panel_ids=["b"], active_id="b"),
        ),
    )
    dock = DockPanel(
        id="dock",
        panels={"a": PanelDef("A"), "b": PanelDef("B")},
        layout=layout,
    )
    wire = _dock_panel_build_split_component(dock, dock.layout, set())  # type: ignore[arg-type]
    assert "mergedTabs" not in wire
