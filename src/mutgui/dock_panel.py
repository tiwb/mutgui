"""DockPanel — 响应式多面板布局组件。

支持二分分割（水平/垂直）、响应式坍缩、Tab 拖拽重排/移动、
Splitter 拖拽、merge_bars 融合 tab 栏。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .action import (
    ActionContext,
    ActionMenu,
    ActionRef,
    ActionRegistry,
    ResolvedAction,
)
from .events import Callback
from .menu import MenuTrigger
from .view import View, ViewBlock

SPLITTER_SIZE = 4
TAB_BAR_SIZE = 36


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ActionDef:
    id: str
    icon: str
    tooltip: str | None = None
    position: Literal["start", "end"] = "end"


@dataclass
class PanelDef:
    id: str
    title: str
    icon: str | None = None
    min_width: int = 0
    min_height: int = 0


@dataclass
class SplitNode:
    direction: Literal["horizontal", "vertical"]
    children: tuple[SplitNode | TabSetNode, SplitNode | TabSetNode]
    id: str | None = None
    ratio: float = 0.5
    merge_bars: bool = False
    collapse_below: int | None = None


@dataclass
class TabSetNode:
    panel_ids: list[str]
    id: str | None = None
    active_id: str | None = None
    bar_position: Literal["top", "bottom", "left", "right"] = "top"
    display_mode: Literal["icon-text", "icon", "icon-active-text"] = "icon-text"
    actions: list[ActionDef | ActionRef] | None = None


LayoutNode = SplitNode | TabSetNode


# ---------------------------------------------------------------------------
# 布局树操作
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
# DockPanel View
# ---------------------------------------------------------------------------

class DockPanel(View):

    def __init__(
        self,
        id: str,
        panels: list[PanelDef],
        layout: LayoutNode,
        default_collapse_below: int = 0,
    ) -> None:
        super().__init__()
        self.id = id
        self.panels: dict[str, PanelDef] = {p.id: p for p in panels}
        self.panel_views: dict[str, View] = {}
        self.layout = layout
        self.default_collapse_below = default_collapse_below
        self.id_counter = 0
        self.viewport_sizes: dict[int, tuple[int, int]] = {}
        self.viewport_collapsed_active: dict[int, dict[str, str]] = {}
        self.viewport_collapsed_orders: dict[int, dict[str, list[str]]] = {}
        self.action_context_data: dict[str, Any] = {}
        self._assign_ids(layout)

    def _next_id(self, prefix: str) -> str:
        self.id_counter += 1
        return f"{prefix}-{self.id_counter}"

    def _assign_ids(self, node: LayoutNode) -> None:
        if isinstance(node, SplitNode):
            if node.id is None:
                node.id = self._next_id("split")
            self._assign_ids(node.children[0])
            self._assign_ids(node.children[1])
        else:
            if node.id is None:
                node.id = self._next_id("tabset")
            if node.active_id is None and node.panel_ids:
                node.active_id = node.panel_ids[0]

    def set_panel_view(self, panel_id: str, view: View) -> None:
        view.id = panel_id
        self.panel_views[panel_id] = view

    # -- Render --

    def render(self) -> ViewBlock:
        self._cleanup_viewports()

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
                self._on_resize,
                width="$0.width", height="$0.height",
                viewport_id="@event.viewport_id",
            ),
            "onTabSwitch": Callback(
                self._on_tab_switch,
                tabsetId="$0.tabsetId", panelId="$0.panelId",
                viewport_id="@event.viewport_id",
            ),
            "onTabReorder": Callback(
                self._on_tab_reorder,
                tabsetId="$0.tabsetId", panelIds="$0.panelIds",
                viewport_id="@event.viewport_id",
            ),
            "onTabMove": Callback(
                self._on_tab_move,
                fromTabset="$0.fromTabset", toTabset="$0.toTabset",
                panelId="$0.panelId", index="$0.index",
            ),
            "onSplitResize": Callback(
                self._on_split_resize,
                splitId="$0.splitId", ratio="$0.ratio",
            ),
            "onActionClick": Callback(
                self._on_action_click,
                tabsetId="$0.tabsetId", actionId="$0.actionId",
            ),
            "onTabDock": Callback(
                self._on_tab_dock,
                fromTabset="$0.fromTabset", panelId="$0.panelId",
                targetTabset="$0.targetTabset", position="$0.position",
            ),
            "onEdgeDock": Callback(
                self._on_edge_dock,
                fromTabset="$0.fromTabset", panelId="$0.panelId",
                edge="$0.edge",
            ),
            "$children": all_views,
        }])

    def _build_wire_node(self, node: LayoutNode,
                         collapsed_ids: set[str]) -> dict[str, Any]:
        if isinstance(node, TabSetNode):
            return self._build_tabset_wire(node, collapsed_ids)
        return self._build_split_wire(node, collapsed_ids)

    def _build_tabset_wire(self, node: TabSetNode,
                           collapsed_ids: set[str]) -> dict[str, Any]:
        tabs: list[dict[str, Any]] = []
        for pid in node.panel_ids:
            p = self.panels.get(pid)
            if p:
                tab: dict[str, Any] = {"id": p.id, "title": p.title}
                if p.icon:
                    tab["icon"] = p.icon
                tabs.append(tab)

        active_id = node.active_id
        children: list[dict[str, Any]] = (
            [{"$view": active_id}]
            if active_id and active_id in self.panel_views else []
        )
        result: dict[str, Any] = {
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
            result["actions"] = self._build_tabset_actions(node)
        if node.id and node.id in collapsed_ids:
            result["collapsed"] = True
        return result

    def _build_tabset_actions(self, node: TabSetNode) -> list[dict[str, Any]]:
        context = self._tabset_action_context(node)
        wire_actions: list[dict[str, Any]] = []
        buffered_refs: list[ActionRef] = []

        def flush_refs() -> None:
            nonlocal buffered_refs
            if not buffered_refs:
                return
            resolved = ActionRegistry.resolve(context=context, refs=buffered_refs)
            for item in resolved:
                wire_actions.append(self._wire_tabset_action(
                    item,
                    context=context,
                    index=len(wire_actions),
                ))
            buffered_refs = []

        for action in node.actions or []:
            if isinstance(action, ActionDef):
                flush_refs()
                wire_actions.append({
                    "id": action.id,
                    "icon": action.icon,
                    "tooltip": action.tooltip,
                    "position": action.position,
                    "groupName": "",
                })
                continue
            buffered_refs.append(action)
        flush_refs()
        return wire_actions

    def _wire_tabset_action(
        self,
        item: ResolvedAction,
        *,
        context: ActionContext,
        index: int,
    ) -> dict[str, Any]:
        node: dict[str, Any] = {
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
            node["onClick"] = Callback(
                lambda action=item.action, ctx=context:
                action.execute(ctx),
            )
        if item.variant in {"dropdown", "split"}:
            node["onMenuClick"] = MenuTrigger(
                lambda action=item.action, ctx=context:
                    ActionMenu(
                        owner=self,
                        source_action=action,
                        context=ctx.with_updates(surface="menu"),
                    ),
                placement="bottom-start",
            )
        return node

    def _tabset_action_context(self, node: TabSetNode) -> ActionContext:
        data = {
            "dock_panel": self,
            "tabset_id": node.id,
            "tabset": node,
            "active_panel_id": node.active_id,
        }
        data.update(self.action_context_data)
        return ActionContext(
            owner=self,
            surface="dock",
            data=data,
        )

    def _build_split_wire(self, node: SplitNode,
                          collapsed_ids: set[str]) -> dict[str, Any]:
        c0_wire = self._build_wire_node(node.children[0], collapsed_ids)
        c1_wire = self._build_wire_node(node.children[1], collapsed_ids)

        result: dict[str, Any] = {
            "$component": "mutgui.DockPanel.Split",
            "$id": node.id,
            "nodeId": node.id,
            "direction": node.direction,
            "ratio": node.ratio,
            "mergeBars": node.merge_bars,
            "$children": [c0_wire, c1_wire],
        }

        if (node.merge_bars
                and isinstance(node.children[0], TabSetNode)
                and isinstance(node.children[1], TabSetNode)):
            left = node.children[0]
            right = node.children[1]
            c0_wire["hideBar"] = True
            c1_wire["hideBar"] = True
            result["mergedTabs"] = {
                "left": self._tabs_for_node(left),
                "right": self._tabs_for_node(right),
                "leftTabsetId": left.id,
                "rightTabsetId": right.id,
                "leftActiveId": left.active_id,
                "rightActiveId": right.active_id,
            }

        return result

    def _tabs_for_node(self, node: TabSetNode) -> list[dict[str, Any]]:
        tabs: list[dict[str, Any]] = []
        for pid in node.panel_ids:
            p = self.panels.get(pid)
            if p:
                tab: dict[str, Any] = {"id": p.id, "title": p.title}
                if p.icon:
                    tab["icon"] = p.icon
                tabs.append(tab)
        return tabs

    # -- Collapse --

    def _compute_layout(
        self, node: LayoutNode, width: int, height: int,
        channel_id: int = 0,
        collapsed_ids: set[str] | None = None,
    ) -> LayoutNode:
        if isinstance(node, TabSetNode):
            return node
        axis = node.direction
        total = width if axis == "horizontal" else height

        threshold = (node.collapse_below if node.collapse_below is not None
                     else self.default_collapse_below)
        if threshold > 0 and total < threshold:
            all_panels = collect_all_panels(node)
            vp_orders = self.viewport_collapsed_orders.get(channel_id, {})
            stored = vp_orders.get(node.id or "")
            if stored and set(stored) == set(all_panels):
                all_panels = stored
            vp_active = self.viewport_collapsed_active.get(channel_id, {})
            active = vp_active.get(node.id or "")
            if not active or active not in all_panels:
                active = find_active_in_subtree(node)
            if collapsed_ids is not None:
                collapsed_ids.add(node.id or "")
            return TabSetNode(
                panel_ids=all_panels,
                id=node.id,
                active_id=active,
            )

        c0_size = int(total * node.ratio)
        c1_size = total - c0_size
        if axis == "horizontal":
            c0 = self._compute_layout(
                node.children[0], c0_size, height, channel_id, collapsed_ids)
            c1 = self._compute_layout(
                node.children[1], c1_size, height, channel_id, collapsed_ids)
        else:
            c0 = self._compute_layout(
                node.children[0], width, c0_size, channel_id, collapsed_ids)
            c1 = self._compute_layout(
                node.children[1], width, c1_size, channel_id, collapsed_ids)

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

    # -- Per-viewport --

    def render_viewport(
        self, wire_tree: list[dict[str, Any]], channel_id: int,
    ) -> list[dict[str, Any]]:
        from ._view_impl import _process_node

        size = self.viewport_sizes.get(channel_id)
        if not size:
            return wire_tree
        collapsed_ids: set[str] = set()
        render_tree = self._compute_layout(
            self.layout, *size, channel_id, collapsed_ids)
        vp_wire = _process_node(self, self._build_wire_node(render_tree, collapsed_ids))
        if wire_tree:
            return [{**wire_tree[0], "$children": [vp_wire]}, *wire_tree[1:]]
        return wire_tree

    def _cleanup_viewports(self) -> None:
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
        self.viewport_sizes = {
            k: v for k, v in self.viewport_sizes.items() if k in active_ids}
        self.viewport_collapsed_active = {
            k: v for k, v in self.viewport_collapsed_active.items()
            if k in active_ids}
        self.viewport_collapsed_orders = {
            k: v for k, v in self.viewport_collapsed_orders.items()
            if k in active_ids}

    # -- Event handlers --

    def _on_resize(self, *, width: int, height: int,
                   viewport_id: int) -> None:
        self.viewport_sizes[viewport_id] = (width, height)
        self.invalidate()

    def _on_tab_switch(self, *, tabsetId: str, panelId: str,
                       viewport_id: int) -> None:
        node = find_node(self.layout, tabsetId)
        if isinstance(node, TabSetNode):
            if panelId in node.panel_ids:
                node.active_id = panelId
                self.invalidate()
        elif isinstance(node, SplitNode):
            vp_active = self.viewport_collapsed_active.setdefault(
                viewport_id, {})
            vp_active[tabsetId] = panelId
            self.invalidate()

    def _on_tab_reorder(self, *, tabsetId: str,
                        panelIds: list[str],
                        viewport_id: int) -> None:
        node = find_node(self.layout, tabsetId)
        if isinstance(node, TabSetNode):
            if set(panelIds) == set(node.panel_ids):
                node.panel_ids = list(panelIds)
                self.invalidate()
        elif isinstance(node, SplitNode):
            all_panels = collect_all_panels(node)
            if set(panelIds) == set(all_panels):
                vp_orders = self.viewport_collapsed_orders.setdefault(
                    viewport_id, {})
                vp_orders[tabsetId] = list(panelIds)
                self.invalidate()

    def _on_tab_move(self, *, fromTabset: str, toTabset: str,
                     panelId: str, index: int) -> None:
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

    def _on_split_resize(self, *, splitId: str, ratio: float) -> None:
        node = find_node(self.layout, splitId)
        if isinstance(node, SplitNode):
            node.ratio = max(0.0, min(1.0, ratio))
            self.invalidate()

    def _on_action_click(self, *, tabsetId: str, actionId: str) -> None:
        pass

    def _on_tab_dock(self, *, fromTabset: str, panelId: str,
                     targetTabset: str, position: str) -> None:
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
        new_tabset.id = self._next_id("tabset")

        if position in ("left", "top"):
            children: tuple[LayoutNode, LayoutNode] = (new_tabset, dst)
        else:
            children = (dst, new_tabset)

        new_split = SplitNode(direction=direction, children=children,
                              ratio=0.5)
        new_split.id = self._next_id("split")

        self.layout = replace_node(self.layout, targetTabset, new_split)
        self.layout = cleanup_tree(self.layout)
        self.invalidate()

    def _on_edge_dock(self, *, fromTabset: str, panelId: str,
                      edge: str) -> None:
        src = find_node(self.layout, fromTabset)
        if src is None:
            return
        if not remove_panel_from_subtree(src, panelId):
            return

        direction: Literal["horizontal", "vertical"] = (
            "horizontal" if edge in ("left", "right") else "vertical")
        new_tabset = TabSetNode(panel_ids=[panelId], active_id=panelId)
        new_tabset.id = self._next_id("tabset")

        if edge in ("left", "top"):
            children: tuple[LayoutNode, LayoutNode] = (
                new_tabset, self.layout)
        else:
            children = (self.layout, new_tabset)

        new_root = SplitNode(direction=direction, children=children,
                             ratio=0.5)
        new_root.id = self._next_id("split")

        self.layout = cleanup_tree(new_root)
        self.invalidate()
