"""Action Declaration 实现 — @impl for Action, ActionCategoryProvider, ActionMenu, ActionToolbar."""

from __future__ import annotations

from typing import Any, Literal

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
from .view import View, ViewBlock


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
    items: list[dict[str, Any] | View] = []

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
) -> list[dict[str, Any] | View]:
    items: list[dict[str, Any] | View] = []
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
) -> list[dict[str, Any] | View]:
    rendered: list[dict[str, Any] | View] = []
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

        node: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# ActionToolbar — render + private helpers
# ---------------------------------------------------------------------------

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
        "$component": "div",
        "$id": "toolbar",
        "style": {
            "display": "flex",
            "alignItems": "center",
            "width": "100%",
            "gap": f"{self.gap}px",
        },
        "$children": [
            {
                "$component": "div",
                "$id": "start",
                "style": {
                    "display": "flex",
                    "gap": f"{self.gap}px",
                    "alignItems": "center",
                    "flexWrap": "wrap" if self.wrap else "nowrap",
                },
                "$children": [
                    *_toolbar_render_action_strip(
                        self, start_actions, context, start_index=0,
                    ),
                ],
            },
            {
                "$component": "div",
                "$id": "spacer",
                "style": {"flex": 1},
            },
            {
                "$component": "div",
                "$id": "end",
                "style": {
                    "display": "flex",
                    "gap": f"{self.gap}px",
                    "alignItems": "center",
                    "flexWrap": "wrap" if self.wrap else "nowrap",
                },
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
) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    prev_group_name: str | None = None
    for offset, item in enumerate(actions, start=start_index):
        if rendered and item.group_name != prev_group_name:
            rendered.append(_toolbar_group_separator(offset))
        rendered.append(_toolbar_render_action(self, item, context, offset))
        prev_group_name = item.group_name
    return rendered


def _toolbar_render_action(
    self: ActionToolbar,
    item: ResolvedAction,
    context: ActionContext,
    index: int,
) -> dict[str, Any]:
    if item.variant == "widget" and item.toolbar_view is not None:
        widget = _toolbar_ensure_view_id(
            self,
            item.toolbar_view,
            f"toolbar-widget-{item.ref_id}-{index}",
        )
        return {
            "$component": "div",
            "$id": f"widget-{index}",
            "title": item.tooltip,
            "style": {
                "display": "inline-flex",
                "alignItems": "center",
                "minHeight": "32px",
            },
            "$children": [widget],
        }

    if item.variant == "split":
        return {
            "$component": "div",
            "$id": f"split-{index}",
            "style": {
                "display": "inline-flex",
                "alignItems": "stretch",
            },
            "$children": [
                _toolbar_button_schema(
                    self,
                    item,
                    component_id=f"main-{index}",
                    on_click=(
                        Callback(item.action.execute, context)
                        if item.can_execute and item.enabled
                        else None
                    ),
                    left_rounded=True,
                    right_rounded=False,
                ),
                _toolbar_button_schema(
                    self,
                    item,
                    component_id=f"menu-{index}",
                    on_click=MenuTrigger(
                        ActionMenu,
                        source_action=item.action,
                        context=context,
                        placement=item.menu_placement,
                    ),
                    disabled=False,
                    label=_menu_arrow(item.menu_placement),
                    use_icon=False,
                    left_rounded=False,
                    right_rounded=True,
                ),
            ],
        }

    if item.variant == "dropdown":
        return _toolbar_button_schema(
            self,
            item,
            component_id=f"dropdown-{index}",
            on_click=MenuTrigger(
                ActionMenu,
                source_action=item.action,
                context=context,
                placement=item.menu_placement,
            ),
            show_menu_arrow=True,
            menu_arrow=_menu_arrow(item.menu_placement),
        )

    return _toolbar_button_schema(
        self,
        item,
        component_id=f"button-{index}",
        on_click=(
            Callback(item.action.execute, context)
            if item.can_execute and item.enabled
            else None
        ),
    )


def _toolbar_button_schema(
    self: ActionToolbar,
    item: ResolvedAction,
    *,
    component_id: str,
    on_click: Callback | MenuTrigger | None,
    disabled: bool | None = None,
    label: str | None = None,
    use_icon: bool = True,
    show_menu_arrow: bool = False,
    menu_arrow: str = "▾",
    left_rounded: bool = True,
    right_rounded: bool = True,
) -> dict[str, Any]:
    children = _toolbar_button_children(
        self,
        item.icon if use_icon else None,
        label or item.label,
        show_menu_arrow=show_menu_arrow,
        menu_arrow=menu_arrow,
    )
    style: dict[str, Any] = {
        "display": "inline-flex",
        "alignItems": "center",
        "gap": "6px",
        "height": "32px",
        "padding": "0 10px",
        "border": "1px solid var(--mutgui-border, #d9d9d9)",
        "background": (
            "color-mix(in oklch, var(--mutgui-accent) 22%, var(--mutgui-bg))"
            if item.checked
            else "var(--mutgui-bg, #fff)"
        ),
        "color": "var(--mutgui-text, #111)",
        "cursor": "pointer",
        "borderTopLeftRadius": "6px" if left_rounded else "0",
        "borderBottomLeftRadius": "6px" if left_rounded else "0",
        "borderTopRightRadius": "6px" if right_rounded else "0",
        "borderBottomRightRadius": "6px" if right_rounded else "0",
    }
    node: dict[str, Any] = {
        "$component": "button",
        "$id": component_id,
        "type": "button",
        "title": _toolbar_button_title(item),
        "disabled": (not item.enabled) if disabled is None else disabled,
        "style": style,
    }
    if on_click is not None:
        node["onClick"] = on_click
    if isinstance(children, list):
        node["$children"] = children
    else:
        node["children"] = children
    return node


def _toolbar_button_children(
    self: ActionToolbar,
    icon: str | None,
    label: str,
    *,
    show_menu_arrow: bool = False,
    menu_arrow: str = "▾",
) -> list[dict[str, Any]] | str:
    mode = _toolbar_effective_label_mode(self)
    if icon is not None and mode == "icon-only":
        if not show_menu_arrow:
            return icon
        children: list[dict[str, Any]] = [
            {"$component": "span", "$id": "icon", "children": icon},
        ]
    elif icon and label:
        children = [
            {"$component": "span", "$id": "icon", "children": icon},
            {"$component": "span", "$id": "label", "children": label},
        ]
    else:
        text = icon or label
        if not show_menu_arrow:
            return text
        children = [
            {"$component": "span", "$id": "label", "children": text},
        ]
    if show_menu_arrow:
        children.append(
            {"$component": "span", "$id": "arrow", "children": menu_arrow}
        )
    return children


def _toolbar_button_title(item: ResolvedAction) -> str:
    title = item.tooltip or item.label
    if item.shortcut:
        return f"{title} ({item.shortcut})"
    return title


def _toolbar_effective_label_mode(
    self: ActionToolbar,
) -> Literal["always", "icon-only"]:
    if self.label_mode == "icon-only":
        return "icon-only"
    return "always"


def _toolbar_group_separator(index: int) -> dict[str, Any]:
    return {
        "$component": "div",
        "$id": f"divider-{index}",
        "ariaHidden": True,
        "style": {
            "width": "1px",
            "height": "20px",
            "alignSelf": "center",
            "background": "var(--mutgui-border, #d9d9d9)",
        },
    }


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
