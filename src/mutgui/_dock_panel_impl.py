"""DockPanel Declaration 实现。

所有 DockPanel 方法的实际实现 + 布局树工具函数 + 事件回调，
通过 @impl 注册到声明侧。
"""

from __future__ import annotations

from typing import Any, Literal

import mutobj
from mutobj import impl

from .action import ActionContext
from ._action_registry import resolve_actions, ResolvedAction
from .dock_panel import DockPanel, LayoutNode, PanelDef, SplitNode, TabSetNode
from .events import Callback
from .expr import Expr
from .view import ViewBlock, RenderComponent, RenderValue, WireTree, WireValue, View, RenderTree

SPLITTER_SIZE = 4
TAB_BAR_SIZE = 36


# ---------------------------------------------------------------------------
# Extension — DockPanel 运行时私有状态
# ---------------------------------------------------------------------------

class DockPanelRuntime(mutobj.Extension[DockPanel]):
    """DockPanel 的运行时私有状态 — viewport 响应式坍缩内部簿记。"""
    viewport_sizes: dict[int, tuple[int, int]] = mutobj.field(default_factory=dict)
    viewport_collapsed_active: dict[int, dict[str, str]] = mutobj.field(default_factory=dict)
    viewport_collapsed_orders: dict[int, dict[str, list[str]]] = mutobj.field(default_factory=dict)
    id_counter: int = 0
    action_context_data: dict[str, Any] = mutobj.field(default_factory=dict)


def _dp_ext(self: DockPanel) -> DockPanelRuntime:
    return DockPanelRuntime.get_or_create(self)


# ---------------------------------------------------------------------------
# 布局树工具函数
# ---------------------------------------------------------------------------

def collect_all_panels(node: LayoutNode) -> list[str]:
    if isinstance(node, TabSetNode):
        return list(node.panel_ids)
    return (collect_all_panels(node.children[0])
            + collect_all_panels(node.children[1]))


def find_node(root: LayoutNode, node_id: str) -> LayoutNode | None:
    if root.id == node_id:
        return root
    if isinstance(root, SplitNode):
        return (find_node(root.children[0], node_id)
                or find_node(root.children[1], node_id))
    return None


def cleanup_tree(root: LayoutNode) -> LayoutNode:
    if isinstance(root, TabSetNode):
        return root
    c0 = cleanup_tree(root.children[0])
    c1 = cleanup_tree(root.children[1])
    if isinstance(c0, TabSetNode) and not c0.panel_ids:
        return c1
    if isinstance(c1, TabSetNode) and not c1.panel_ids:
        return c0
    merge_bars = root.merge_bars
    if merge_bars and not (isinstance(c0, TabSetNode)
                           and isinstance(c1, TabSetNode)):
        merge_bars = False
    if (c0 is root.children[0] and c1 is root.children[1]
            and merge_bars == root.merge_bars):
        return root
    return SplitNode(
        direction=root.direction,
        children=(c0, c1),
        id=root.id,
        ratio=root.ratio,
        merge_bars=merge_bars,
        collapse_below=root.collapse_below,
    )


def replace_node(root: LayoutNode, node_id: str,
                 new_node: LayoutNode) -> LayoutNode:
    if root.id == node_id:
        return new_node
    if isinstance(root, SplitNode):
        c0 = replace_node(root.children[0], node_id, new_node)
        c1 = replace_node(root.children[1], node_id, new_node)
        if c0 is root.children[0] and c1 is root.children[1]:
            return root
        return SplitNode(
            direction=root.direction,
            children=(c0, c1),
            id=root.id,
            ratio=root.ratio,
            merge_bars=root.merge_bars,
            collapse_below=root.collapse_below,
        )
    return root


def remove_panel_from_subtree(node: LayoutNode, panel_id: str) -> bool:
    if isinstance(node, TabSetNode):
        if panel_id in node.panel_ids:
            node.panel_ids.remove(panel_id)
            if node.active_id == panel_id:
                node.active_id = (node.panel_ids[0]
                                  if node.panel_ids else None)
            return True
        return False
    return (remove_panel_from_subtree(node.children[0], panel_id)
            or remove_panel_from_subtree(node.children[1], panel_id))


def find_parent_split(root: LayoutNode, node_id: str) -> SplitNode | None:
    if isinstance(root, SplitNode):
        for child in root.children:
            if child.id == node_id:
                return root
            result = find_parent_split(child, node_id)
            if result is not None:
                return result
    return None


def find_active_in_subtree(node: LayoutNode) -> str | None:
    if isinstance(node, TabSetNode):
        return node.active_id
    return (find_active_in_subtree(node.children[0])
            or find_active_in_subtree(node.children[1]))


def set_active_in_subtree(node: LayoutNode, panel_id: str) -> bool:
    if isinstance(node, TabSetNode):
        if panel_id in node.panel_ids:
            node.active_id = panel_id
            return True
        return False
    return (set_active_in_subtree(node.children[0], panel_id)
            or set_active_in_subtree(node.children[1], panel_id))


# ---------------------------------------------------------------------------
# DockPanel @impl 方法
# ---------------------------------------------------------------------------

@impl(DockPanel.__init__)
def dock_panel_init(
    self: DockPanel,
    id: str,
    panels: list[PanelDef],
    layout: LayoutNode,
    default_collapse_below: int = 0,
) -> None:
    super(DockPanel, self).__init__()
    self.id = id
    self.panels = {p.id: p for p in panels}
    self.panel_views = {}
    self.layout = layout
    self.default_collapse_below = default_collapse_below
    ext = _dp_ext(self)
    ext.id_counter = 0
    ext.viewport_sizes = {}
    ext.viewport_collapsed_active = {}
    ext.viewport_collapsed_orders = {}
    ext.action_context_data = {}
    _dock_panel_assign_ids(self, layout)


@impl(DockPanel.set_panel_view)
def dock_panel_set_panel_view(self: DockPanel, panel_id: str, view: View) -> None:
    view.id = panel_id
    self.panel_views[panel_id] = view


@impl(DockPanel.render)
def dock_panel_render(self: DockPanel) -> ViewBlock:
    _dock_panel_cleanup_viewports(self)

    panels_data: dict[str, Any] = {}
    for p in self.panels.values():
        panels_data[p.id] = {
            "title": p.title,
            "icon": p.icon,
            "minWidth": p.min_width,
            "minHeight": p.min_height,
        }

    all_views = list(self.panel_views.values())

    return ViewBlock([{
        "$component": "mutgui.DockPanel",
        "$id": "dock",
        "panels": panels_data,
        "onResize": Callback(
            _dock_panel_on_resize,
            self,
            width=Expr.wire("$0.width"), height=Expr.wire("$0.height"),
            viewport_id=Expr.host("event.viewport_id"),
        ),
        "onTabSwitch": Callback(
            _dock_panel_on_tab_switch,
            self,
            tabsetId=Expr.wire("$0.tabsetId"), panelId=Expr.wire("$0.panelId"),
            viewport_id=Expr.host("event.viewport_id"),
        ),
        "onTabReorder": Callback(
            _dock_panel_on_tab_reorder,
            self,
            tabsetId=Expr.wire("$0.tabsetId"), panelIds=Expr.wire("$0.panelIds"),
            viewport_id=Expr.host("event.viewport_id"),
        ),
        "onTabMove": Callback(
            _dock_panel_on_tab_move,
            self,
            fromTabset=Expr.wire("$0.fromTabset"), toTabset=Expr.wire("$0.toTabset"),
            panelId=Expr.wire("$0.panelId"), index=Expr.wire("$0.index"),
        ),
        "onSplitResize": Callback(
            _dock_panel_on_split_resize,
            self,
            splitId=Expr.wire("$0.splitId"), ratio=Expr.wire("$0.ratio"),
        ),
        "onActionClick": Callback(
            _dock_panel_on_action_click,
            self,
            tabsetId=Expr.wire("$0.tabsetId"), actionId=Expr.wire("$0.actionId"),
        ),
        "onTabDock": Callback(
            _dock_panel_on_tab_dock,
            self,
            fromTabset=Expr.wire("$0.fromTabset"), panelId=Expr.wire("$0.panelId"),
            targetTabset=Expr.wire("$0.targetTabset"), position=Expr.wire("$0.position"),
        ),
        "onEdgeDock": Callback(
            _dock_panel_on_edge_dock,
            self,
            fromTabset=Expr.wire("$0.fromTabset"), panelId=Expr.wire("$0.panelId"),
            edge=Expr.wire("$0.edge"),
        ),
        "$children": all_views,
    }])


@impl(DockPanel.render_viewport)
def dock_panel_render_viewport(
    self: DockPanel, wire_tree: WireTree, channel_id: int,
) -> WireTree:
    size = _dp_ext(self).viewport_sizes.get(channel_id)
    if not size:
        return wire_tree
    collapsed_ids: set[str] = set()
    layout = _dock_panel_compute_layout(self, self.layout, *size, channel_id, collapsed_ids)
    vp_node = self.render_to_wire(_dock_panel_build_component(self, layout, collapsed_ids))
    if wire_tree:
        return [{**wire_tree[0], "$children": [vp_node]}, *wire_tree[1:]]
    return wire_tree


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _dock_panel_next_id(self: DockPanel, prefix: str) -> str:
    ext = _dp_ext(self)
    ext.id_counter += 1
    return f"{prefix}-{ext.id_counter}"


def _dock_panel_assign_ids(self: DockPanel, node: LayoutNode) -> None:
    if isinstance(node, SplitNode):
        if node.id is None:
            node.id = _dock_panel_next_id(self, "split")
        _dock_panel_assign_ids(self, node.children[0])
        _dock_panel_assign_ids(self, node.children[1])
    else:
        if node.id is None:
            node.id = _dock_panel_next_id(self, "tabset")
        if node.active_id is None and node.panel_ids:
            node.active_id = node.panel_ids[0]


def _dock_panel_cleanup_viewports(self: DockPanel) -> None:
    from ._view_impl import ViewObservers
    from ._viewport_impl import ViewPortRuntime
    obs = ViewObservers.get(self)
    if obs is None:
        return
    active_ids: set[int] = set()
    for vp in obs.viewports:
        rt = ViewPortRuntime.get(vp)
        if rt is not None and rt.channel is not None:
            active_ids.add(rt.channel.channel_id)
    ext = _dp_ext(self)
    ext.viewport_sizes = {
        k: v for k, v in ext.viewport_sizes.items() if k in active_ids}
    ext.viewport_collapsed_active = {
        k: v for k, v in ext.viewport_collapsed_active.items()
        if k in active_ids}
    ext.viewport_collapsed_orders = {
        k: v for k, v in ext.viewport_collapsed_orders.items()
        if k in active_ids}


# -- Wire tree construction --

def _dock_panel_build_component(
    self: DockPanel, node: LayoutNode, collapsed_ids: set[str],
) -> RenderComponent:
    if isinstance(node, TabSetNode):
        return _dock_panel_build_tabset_component(self, node, collapsed_ids)
    return _dock_panel_build_split_component(self, node, collapsed_ids)


def _dock_panel_build_tabset_component(
    self: DockPanel, node: TabSetNode, collapsed_ids: set[str],
) -> RenderComponent:
    tabs: list[RenderComponent] = []
    for pid in node.panel_ids:
        p = self.panels.get(pid)
        if p:
            tab: RenderComponent = {"id": p.id, "title": p.title}
            if p.icon:
                tab["icon"] = p.icon
            tabs.append(tab)

    active_id = node.active_id
    active_view = self.panel_views.get(active_id) if active_id else None
    children: RenderTree = [active_view] if active_view else []
    result: RenderComponent = {
        "$component": "mutgui.DockPanel.TabSet",
        "$id": node.id,
        "nodeId": node.id,
        "tabs": tabs,
        "activeId": active_id,
        "barPosition": node.bar_position,
        "displayMode": node.display_mode,
        "$children": children,
    }
    if node.actions:
        result["actions"] = _dock_panel_build_tabset_actions(self, node)
    if node.id and node.id in collapsed_ids:
        result["collapsed"] = True
    return result


def _dock_panel_build_tabset_actions(
    self: DockPanel, node: TabSetNode,
) -> list[RenderValue]:
    context = _dock_panel_tabset_action_context(self, node)
    render_actions: list[RenderValue] = []
    resolved = resolve_actions(context=context, refs=node.actions or [])
    for item in resolved:
        render_actions.append(_dock_panel_build_action(
            self,
            item,
            context=context,
            index=len(render_actions),
        ))
    return render_actions


def _dock_panel_build_action(
    self: DockPanel,
    item: ResolvedAction,
    *,
    context: ActionContext,
    index: int,
) -> RenderComponent:
    node: RenderComponent = {
        "id": item.ref_id,
        "icon": item.icon,
        "label": item.label,
        "tooltip": item.tooltip,
        "position": item.position,
        "variant": item.variant,
        "checked": item.checked,
        "disabled": not item.enabled,
        "groupName": item.group_name,
    }
    if item.variant == "widget" and item.toolbar_view is not None:
        node["$children"] = item.toolbar_view.render().items
        return node
    if item.can_execute and item.enabled:
        node["onClick"] = Callback(item.action.execute, context)
    if item.variant in {"dropdown", "split"}:
        from .action import ActionMenu
        from .menu import MenuTrigger

        menu_context = context.with_updates(surface="menu")
        node["onMenuClick"] = MenuTrigger(
            ActionMenu,
            source_action=item.action,
            context=menu_context,
            placement="bottom-start",
        )
    return node


def _dock_panel_tabset_action_context(
    self: DockPanel, node: TabSetNode,
) -> ActionContext:
    data: dict[str, Any] = {
        "dock_panel": self,
        "tabset_id": node.id,
        "tabset": node,
        "active_panel_id": node.active_id,
    }
    data.update(_dp_ext(self).action_context_data)
    return ActionContext(
        surface="dock",
        data=data,
    )


def _dock_panel_build_split_component(
    self: DockPanel, node: SplitNode, collapsed_ids: set[str],
) -> RenderComponent:
    c0_component = _dock_panel_build_component(self, node.children[0], collapsed_ids)
    c1_component = _dock_panel_build_component(self, node.children[1], collapsed_ids)

    result: RenderComponent = {
        "$component": "mutgui.DockPanel.Split",
        "$id": node.id,
        "nodeId": node.id,
        "direction": node.direction,
        "ratio": node.ratio,
        "mergeBars": node.merge_bars,
        "$children": [c0_component, c1_component],
    }

    if (node.merge_bars
            and isinstance(node.children[0], TabSetNode)
            and isinstance(node.children[1], TabSetNode)):
        left = node.children[0]
        right = node.children[1]
        c0_component["hideBar"] = True
        c1_component["hideBar"] = True
        result["mergedTabs"] = {
            "left": _dock_panel_tabs_for_node(self, left),
            "right": _dock_panel_tabs_for_node(self, right),
            "leftTabsetId": left.id,
            "rightTabsetId": right.id,
            "leftActiveId": left.active_id,
            "rightActiveId": right.active_id,
        }

    return result


def _dock_panel_tabs_for_node(
    self: DockPanel, node: TabSetNode,
) -> WireTree:
    tabs: WireTree = []
    for pid in node.panel_ids:
        p = self.panels.get(pid)
        if p:
            tab: dict[str, WireValue] = {"id": p.id, "title": p.title}
            if p.icon:
                tab["icon"] = p.icon
            tabs.append(tab)
    return tabs


# -- Collapse --

def _dock_panel_compute_layout(
    self: DockPanel, node: LayoutNode, width: int, height: int,
    channel_id: int,
    collapsed_ids: set[str],
) -> LayoutNode:
    if isinstance(node, TabSetNode):
        return node
    axis = node.direction
    total = width if axis == "horizontal" else height

    threshold = (node.collapse_below if node.collapse_below is not None
                 else self.default_collapse_below)
    if threshold > 0 and total < threshold:
        ext = _dp_ext(self)
        all_panels = collect_all_panels(node)
        vp_orders = ext.viewport_collapsed_orders.get(channel_id, {})
        stored = vp_orders.get(node.id or "")
        if stored and set(stored) == set(all_panels):
            all_panels = stored
        vp_active = ext.viewport_collapsed_active.get(channel_id, {})
        active = vp_active.get(node.id or "")
        if not active or active not in all_panels:
            active = find_active_in_subtree(node)
        collapsed_ids.add(node.id or "")
        return TabSetNode(
            panel_ids=all_panels,
            id=node.id,
            active_id=active,
        )

    c0_size = int(total * node.ratio)
    c1_size = total - c0_size
    if axis == "horizontal":
        c0 = _dock_panel_compute_layout(
            self, node.children[0], c0_size, height, channel_id, collapsed_ids)
        c1 = _dock_panel_compute_layout(
            self, node.children[1], c1_size, height, channel_id, collapsed_ids)
    else:
        c0 = _dock_panel_compute_layout(
            self, node.children[0], width, c0_size, channel_id, collapsed_ids)
        c1 = _dock_panel_compute_layout(
            self, node.children[1], width, c1_size, channel_id, collapsed_ids)

    if c0 is node.children[0] and c1 is node.children[1]:
        return node
    return SplitNode(
        direction=node.direction,
        children=(c0, c1),
        id=node.id,
        ratio=node.ratio,
        merge_bars=node.merge_bars,
        collapse_below=node.collapse_below,
    )


# ---------------------------------------------------------------------------
# 事件回调
# ---------------------------------------------------------------------------

def _dock_panel_on_resize(
    self: DockPanel, *, width: int, height: int, viewport_id: int,
) -> None:
    _dp_ext(self).viewport_sizes[viewport_id] = (width, height)
    self.invalidate()


def _dock_panel_on_tab_switch(
    self: DockPanel, *, tabsetId: str, panelId: str, viewport_id: int,
) -> None:
    node = find_node(self.layout, tabsetId)
    if isinstance(node, TabSetNode):
        if panelId in node.panel_ids:
            node.active_id = panelId
            self.invalidate()
    elif isinstance(node, SplitNode):
        vp_active = _dp_ext(self).viewport_collapsed_active.setdefault(
            viewport_id, {})
        vp_active[tabsetId] = panelId
        self.invalidate()


def _dock_panel_on_tab_reorder(
    self: DockPanel, *, tabsetId: str, panelIds: list[str], viewport_id: int,
) -> None:
    node = find_node(self.layout, tabsetId)
    if isinstance(node, TabSetNode):
        if set(panelIds) == set(node.panel_ids):
            node.panel_ids = list(panelIds)
            self.invalidate()
    elif isinstance(node, SplitNode):
        all_panels = collect_all_panels(node)
        if set(panelIds) == set(all_panels):
            vp_orders = _dp_ext(self).viewport_collapsed_orders.setdefault(
                viewport_id, {})
            vp_orders[tabsetId] = list(panelIds)
            self.invalidate()


def _dock_panel_on_tab_move(
    self: DockPanel, *, fromTabset: str, toTabset: str,
    panelId: str, index: int,
) -> None:
    src = find_node(self.layout, fromTabset)
    dst = find_node(self.layout, toTabset)
    if src is None or not isinstance(dst, TabSetNode):
        return
    if not remove_panel_from_subtree(src, panelId):
        return
    idx = min(index, len(dst.panel_ids))
    dst.panel_ids.insert(idx, panelId)
    self.layout = cleanup_tree(self.layout)
    self.invalidate()


def _dock_panel_on_split_resize(
    self: DockPanel, *, splitId: str, ratio: float,
) -> None:
    node = find_node(self.layout, splitId)
    if isinstance(node, SplitNode):
        node.ratio = max(0.0, min(1.0, ratio))
        self.invalidate()


def _dock_panel_on_action_click(
    self: DockPanel, *, tabsetId: str, actionId: str,
) -> None:
    pass


def _dock_panel_on_tab_dock(
    self: DockPanel, *, fromTabset: str, panelId: str,
    targetTabset: str, position: str,
) -> None:
    src = find_node(self.layout, fromTabset)
    if src is None:
        return
    if not remove_panel_from_subtree(src, panelId):
        return
    dst = find_node(self.layout, targetTabset)
    if dst is None:
        return

    direction: Literal["horizontal", "vertical"] = (
        "horizontal" if position in ("left", "right") else "vertical")
    new_tabset = TabSetNode(panel_ids=[panelId], active_id=panelId)
    new_tabset.id = _dock_panel_next_id(self, "tabset")

    if position in ("left", "top"):
        children: tuple[LayoutNode, LayoutNode] = (new_tabset, dst)
    else:
        children = (dst, new_tabset)

    new_split = SplitNode(direction=direction, children=children,
                          ratio=0.5)
    new_split.id = _dock_panel_next_id(self, "split")

    self.layout = replace_node(self.layout, targetTabset, new_split)
    self.layout = cleanup_tree(self.layout)
    self.invalidate()


def _dock_panel_on_edge_dock(
    self: DockPanel, *, fromTabset: str, panelId: str, edge: str,
) -> None:
    src = find_node(self.layout, fromTabset)
    if src is None:
        return
    if not remove_panel_from_subtree(src, panelId):
        return

    direction: Literal["horizontal", "vertical"] = (
        "horizontal" if edge in ("left", "right") else "vertical")
    new_tabset = TabSetNode(panel_ids=[panelId], active_id=panelId)
    new_tabset.id = _dock_panel_next_id(self, "tabset")

    if edge in ("left", "top"):
        children: tuple[LayoutNode, LayoutNode] = (
            new_tabset, self.layout)
    else:
        children = (self.layout, new_tabset)

    new_root = SplitNode(direction=direction, children=children,
                         ratio=0.5)
    new_root.id = _dock_panel_next_id(self, "split")

    self.layout = cleanup_tree(new_root)
    self.invalidate()
