"""Action Declaration 实现 — @impl for Action, ActionCategoryProvider, ActionMenu, ActionToolbar."""

from __future__ import annotations

from typing import Any

from mutobj import impl

from .action import (
    Action,
    ActionCategoryProvider,
    ActionContext,
    ActionMenu,
    ActionRef,
    ActionToolbar,
)
from ._action_registry import resolve_actions, ResolvedAction, Stub
from .events import Callback
from .menu import MenuTrigger
from .view import View, ViewBlock, RenderComponent, RenderNode, RenderTree


def _menu_arrow(placement: str) -> str:
    """根据 placement 返回对应的箭头符号。"""
    side = placement.split("-")[0] if "-" in placement else placement
    return {"top": "▴", "bottom": "▾", "left": "◂", "right": "▸"}.get(side, "▾")


# ---------------------------------------------------------------------------
# @impl — Action
# ---------------------------------------------------------------------------

@impl(Action.resolved_action_id)
def action_resolved_action_id(self: Action) -> str:
    if self.action_id:
        return self.action_id
    cls = type(self)
    return f"{cls.__module__}.{cls.__qualname__}"


@impl(Action.resolved_label)
def action_resolved_label(self: Action, context: ActionContext | None = None) -> str:
    return self.label or self.resolved_action_id()


@impl(Action.check_visible)
def action_check_visible(self: Action, context: ActionContext) -> bool:
    return True


@impl(Action.check_enabled)
def action_check_enabled(self: Action, context: ActionContext) -> bool:
    return True


@impl(Action.check_checked)
def action_check_checked(self: Action, context: ActionContext) -> bool:
    return False


@impl(Action.execute, Stub())
def action_execute_stub(self: Action, context: ActionContext) -> Any:
    raise NotImplementedError(
        f"{type(self).__name__}.execute() 未实现"
    )



@impl(Action.toolbar_view)
def action_toolbar_view(self: Action, context: ActionContext) -> View | None:
    return None


@impl(Action.menu_actions)
def action_menu_actions(self: Action, context: ActionContext) -> list[ActionRef]:
    return []


@impl(Action.menu_view)
def action_menu_view(self: Action, context: ActionContext) -> View | None:
    return None


# ---------------------------------------------------------------------------
# @impl — ActionCategoryProvider
# ---------------------------------------------------------------------------

@impl(ActionCategoryProvider.refs)
def action_category_provider_refs(self: ActionCategoryProvider, context: ActionContext) -> list[ActionRef]:
    return []


# ---------------------------------------------------------------------------
# ActionMenu — render + private helpers
# ---------------------------------------------------------------------------

@impl(ActionMenu.render)
def action_menu_render(self: ActionMenu) -> ViewBlock:
    context = _menu_base_context(self).with_updates(surface="menu")
    items: RenderTree = []

    if self.source_action is not None:
        items.extend(
            _menu_render_source_action(self, self.source_action, context)
        )

    resolved = resolve_actions(
        context=context,
        refs=self.refs,
        categories=self.categories,
    )
    if items and resolved:
        items.append({"$component": "mutgui.Menu.Divider"})
    items.extend(_menu_render_resolved_items(self, resolved, context))

    if not items:
        items.append({
            "$component": "mutgui.Menu.Item",
            "$id": "empty",
            "label": self.empty_label,
            "disabled": True,
        })
    return ViewBlock(items)


def _menu_render_source_action(
    self: ActionMenu,
    action: Action,
    context: ActionContext,
) -> RenderTree:
    items: RenderTree = []
    menu_view = action.menu_view(context)
    menu_refs = action.menu_actions(context)
    if menu_view is not None:
        items.append(_menu_ensure_view_id(self, menu_view, "menu-view"))
    if menu_view is not None and menu_refs:
        items.append({"$component": "mutgui.Menu.Divider"})
    if menu_refs:
        resolved = resolve_actions(context=context, refs=menu_refs)
        items.extend(_menu_render_resolved_items(self, resolved, context))
    return items


def _menu_render_resolved_items(
    self: ActionMenu,
    items: list[ResolvedAction],
    context: ActionContext,
) -> RenderTree:
    rendered: RenderTree = []
    prev_group_name: str | None = None
    for index, item in enumerate(items):
        if rendered and item.group_name != prev_group_name:
            rendered.append({"$component": "mutgui.Menu.Divider"})
        if item.menu_view is not None and item.toolbar_view is not None:
            rendered.append(
                _menu_ensure_view_id(
                    self,
                    item.menu_view,
                    f"menu-view-{item.ref_id}-{index}",
                )
            )
            prev_group_name = item.group_name
            continue

        node: RenderComponent = {
            "$component": "mutgui.Menu.Item",
            "$id": f"action-{index}",
            "label": item.label,
            "disabled": not item.enabled,
            "checked": item.checked,
        }
        if item.icon:
            node["icon"] = item.icon
        if item.shortcut:
            node["shortcut"] = item.shortcut
        if item.menu_refs or item.menu_view is not None:
            node["hasSubmenu"] = True
            node["closeOnClick"] = False
            node["onMouseEnter"] = MenuTrigger(
                ActionMenu,
                source_action=item.action,
                context=context,
                placement="right-start",
            )
            rendered.append(node)
            prev_group_name = item.group_name
            continue
        if item.can_execute and item.enabled:
            node["onClick"] = Callback(item.action.execute, context)
        rendered.append(node)
        prev_group_name = item.group_name
    return rendered


def _menu_base_context(self: ActionMenu) -> ActionContext:
    if self.context is not None:
        return self.context
    return ActionContext(surface="menu")


def _menu_ensure_view_id(self: ActionMenu, view: View, suffix: str) -> View:
    if not view.id:
        base = str(self.id or "action-menu")
        if base.startswith("$menu:"):
            base = f"action-view:{base[6:]}"
        view.id = f"{base}:{suffix}"
    return view


@impl(ActionToolbar.render)
def action_toolbar_render(self: ActionToolbar) -> ViewBlock:
    context = _toolbar_base_context(self).with_updates(surface="toolbar")
    actions = resolve_actions(
        context=context,
        refs=self.refs,
        categories=self.categories,
    )
    start_actions = [item for item in actions if item.position == "start"]
    end_actions = [item for item in actions if item.position != "start"]
    return ViewBlock([{
        "$component": "mutgui.Toolbar",
        "$id": "toolbar",
        "$children": [
            {
                "$component": "mutgui.Toolbar.Section",
                "$id": "start",
                "$children": [
                    *_toolbar_render_action_strip(
                        self, start_actions, context, start_index=0,
                    ),
                ],
            },
            {"$component": "mutgui.Toolbar.Spacer"},
            {
                "$component": "mutgui.Toolbar.Section",
                "$id": "end",
                "$children": [
                    *_toolbar_render_action_strip(
                        self,
                        end_actions,
                        context,
                        start_index=len(start_actions),
                    ),
                ],
            },
        ],
    }])


def _toolbar_render_action_strip(
    self: ActionToolbar,
    actions: list[ResolvedAction],
    context: ActionContext,
    *,
    start_index: int,
) -> list[RenderNode]:
    rendered: list[RenderNode] = []
    prev_group_name: str | None = None
    for offset, item in enumerate(actions, start=start_index):
        if rendered and item.group_name != prev_group_name:
            rendered.append({
                "$component": "mutgui.Toolbar.Divider",
                "$id": f"divider-{offset}",
            })
        rendered.append(_toolbar_render_action(self, item, context, offset))
        prev_group_name = item.group_name
    return rendered


def _toolbar_render_action(
    self: ActionToolbar,
    item: ResolvedAction,
    context: ActionContext,
    index: int,
) -> RenderNode:
    # widget variant — 直接嵌入 action 的 toolbar_view
    if item.variant == "widget" and item.toolbar_view is not None:
        widget = _toolbar_ensure_view_id(
            self,
            item.toolbar_view,
            f"toolbar-widget-{item.ref_id}-{index}",
        )
        return widget

    # 公共展示属性
    base_props: RenderComponent = {
        "label": item.label,
        "icon": item.icon,
        "tooltip": item.tooltip,
        "shortcut": item.shortcut,
        "disabled": not item.enabled,
        "checked": item.checked,
        "labelMode": self.label_mode,
    }

    if item.variant == "split":
        split_props: RenderComponent = {
            "$component": "mutgui.Toolbar.SplitButton",
            "$id": f"split-{index}",
            "arrow": _menu_arrow(item.menu_placement),
        }
        split_props.update(base_props)
        if item.can_execute and item.enabled:
            split_props["mainOnClick"] = Callback(item.action.execute, context)
        split_props["menuOnClick"] = MenuTrigger(
            ActionMenu,
            source_action=item.action,
            context=context,
            placement=item.menu_placement,
        )
        return split_props

    if item.variant == "dropdown":
        dropdown_props: RenderComponent = {
            "$component": "mutgui.Toolbar.Dropdown",
            "$id": f"dropdown-{index}",
            "arrow": _menu_arrow(item.menu_placement),
            "onClick": MenuTrigger(
                ActionMenu,
                source_action=item.action,
                context=context,
                placement=item.menu_placement,
            ),
        }
        dropdown_props.update(base_props)
        return dropdown_props

    # default: button variant
    button_props: RenderComponent = {
        "$component": "mutgui.Toolbar.Button",
        "$id": f"button-{index}",
    }
    button_props.update(base_props)
    if item.can_execute and item.enabled:
        button_props["onClick"] = Callback(item.action.execute, context)
    return button_props


def _toolbar_base_context(self: ActionToolbar) -> ActionContext:
    if self.context is not None:
        return self.context
    return ActionContext(surface="toolbar")


def _toolbar_ensure_view_id(
    self: ActionToolbar,
    view: View,
    suffix: str,
) -> View:
    if not view.id:
        base = str(self.id or "action-toolbar")
        view.id = f"{base}:{suffix}"
    return view
