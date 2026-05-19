"""Action 解析引擎 — 将 ActionRef + category 展开为 ResolvedAction 列表。

包含 placement 解析：将字符串 spec 解析为分组/排序键。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import mutobj

from .action import (
    Action,
    ActionCategoryProvider,
    ActionContext,
    ActionPosition,
    ActionRef,
    ActionSource,
    ActionVariant,
)
from .menu import MenuPlacement


class Stub:
    """marker：标记某个 @impl 注册为占位桩，子类必须 override。

    用于 ``@impl(Action.execute, Stub())`` 等场景，consumer 通过
    ``mutobj.impl_meta_of(method, Stub)`` 判断是否为占位实现。
    """


if TYPE_CHECKING:
    from .view import View


# ---------------------------------------------------------------------------
# placement 解析
# ---------------------------------------------------------------------------

PlacementToken = int | str
NormalizedPlacementToken = tuple[int, int | str]
NormalizedPlacement = tuple[NormalizedPlacementToken, ...]


@dataclass(slots=True, frozen=True)
class ParsedPlacement:
    raw: str = ""
    group_name: str = ""
    group_order: tuple[PlacementToken, ...] = ()
    item_order: tuple[PlacementToken, ...] = ()

    @property
    def sort_key(self) -> tuple[NormalizedPlacement, str, NormalizedPlacement]:
        return (
            _normalize_placement_tokens(self.group_order),
            self.group_name,
            _normalize_placement_tokens(self.item_order),
        )


def _parse_placement(spec: str | int | None) -> ParsedPlacement:
    raw = "" if spec is None else str(spec)
    group_part, has_group, item_part = raw.partition("/")
    if not has_group:
        return ParsedPlacement(
            raw=raw,
            group_name="",
            group_order=(),
            item_order=_parse_placement_tokens(raw),
        )
    group_name, group_order = _parse_group_part(group_part)
    return ParsedPlacement(
        raw=raw,
        group_name=group_name,
        group_order=group_order,
        item_order=_parse_placement_tokens(item_part),
    )


def _parse_group_part(spec: str) -> tuple[str, tuple[PlacementToken, ...]]:
    if not spec:
        return "", ()
    tokens = spec.split(":")
    return tokens[0], tuple(_parse_placement_token(token) for token in tokens[1:])


def _parse_placement_tokens(spec: str) -> tuple[PlacementToken, ...]:
    if not spec:
        return ()
    return tuple(_parse_placement_token(token) for token in spec.split(":"))


def _parse_placement_token(token: str) -> PlacementToken:
    try:
        return int(token)
    except ValueError:
        return token


def _normalize_placement_tokens(
    tokens: tuple[PlacementToken, ...],
) -> NormalizedPlacement:
    normalized: list[NormalizedPlacementToken] = []
    for token in tokens:
        if isinstance(token, int):
            normalized.append((0, token))
        else:
            normalized.append((1, token))
    return tuple(normalized)


@dataclass(slots=True)
class ResolvedAction:
    key: str
    ref_id: str
    action_id: str
    action: Action
    label: str
    icon: str | None
    tooltip: str | None
    shortcut: str | None
    placement: str
    group_name: str
    group_order: NormalizedPlacement
    item_order: NormalizedPlacement
    position: ActionPosition
    variant: ActionVariant
    visible: bool
    enabled: bool
    checked: bool
    can_execute: bool
    toolbar_view: View | None
    menu_view: View | None
    menu_refs: list[ActionRef]
    menu_placement: MenuPlacement


# ---------------------------------------------------------------------------
# 解析引擎
# ---------------------------------------------------------------------------


def resolve_actions(
    *,
    context: ActionContext,
    refs: list[ActionRef] | None = None,
    categories: list[str] | None = None,
) -> list[ResolvedAction]:
    resolved: list[ResolvedAction] = []
    seen_categories: set[str] = set()
    refs = refs or []
    categories = categories or []

    for category in categories:
        resolved.extend(_expand_category(
            category,
            context=context.with_updates(category=category),
            seen_categories=seen_categories,
        ))
    for ref in refs:
        resolved.extend(_expand_ref(ref, context=context,
                                    seen_categories=seen_categories))

    visible = _dedupe_resolved([item for item in resolved if item.visible])
    return sorted(visible, key=lambda item: (
        item.group_order,
        item.group_name,
        item.item_order,
    ))


def _expand_ref(
    ref: ActionRef,
    *,
    context: ActionContext,
    seen_categories: set[str],
) -> list[ResolvedAction]:
    if ref.category is not None:
        return _expand_category(
            ref.category,
            context=context.with_updates(category=ref.category),
            seen_categories=seen_categories,
        )

    action = _instantiate_action(ref.action)
    return [_resolve_action(action, ref=ref, context=context)]


def _expand_category(
    category: str,
    *,
    context: ActionContext,
    seen_categories: set[str],
) -> list[ResolvedAction]:
    if category in seen_categories:
        return []
    seen_categories.add(category)
    try:
        refs: list[ActionRef] = []
        for action_cls in _action_classes():
            if category in mutobj.field_default(action_cls.categories):
                refs.append(ActionRef(action=action_cls))
        for provider_cls in _provider_classes():
            if category not in mutobj.field_default(provider_cls.categories):
                continue
            provider = provider_cls()
            refs.extend(provider.refs(context))

        resolved: list[ResolvedAction] = []
        for ref in refs:
            resolved.extend(_expand_ref(
                ref,
                context=context.with_updates(category=category),
                seen_categories=seen_categories,
            ))
        return resolved
    finally:
        seen_categories.remove(category)


def _resolve_action(
    action: Action,
    *,
    ref: ActionRef,
    context: ActionContext,
) -> ResolvedAction:
    action_id = action.resolved_action_id()
    ref_id = ref.ref_id or action_id
    parsed_placement = _resolve_placement(action=action, ref=ref)
    toolbar_view = action.toolbar_view(context.with_updates(surface="toolbar"))
    menu_view = action.menu_view(context.with_updates(surface="menu"))
    menu_refs = action.menu_actions(context.with_updates(surface="menu"))
    can_execute = mutobj.impl_meta_of(type(action).execute, Stub) is None
    variant = _infer_variant(
        action=action,
        ref=ref,
        context=context,
        toolbar_view=toolbar_view,
        menu_view=menu_view,
        menu_refs=menu_refs,
        can_execute=can_execute,
    )
    return ResolvedAction(
        key=f"{ref_id}:{context.surface}",
        ref_id=ref_id,
        action_id=action_id,
        action=action,
        label=ref.label or action.resolved_label(context),
        icon=ref.icon if ref.icon is not None else action.icon,
        tooltip=ref.tooltip if ref.tooltip is not None else action.tooltip,
        shortcut=ref.shortcut if ref.shortcut is not None else action.shortcut,
        placement=parsed_placement.raw,
        group_name=parsed_placement.group_name,
        group_order=parsed_placement.sort_key[0],
        item_order=parsed_placement.sort_key[2],
        position=ref.position or action.position,
        variant=variant,
        visible=action.check_visible(context),
        enabled=action.check_enabled(context),
        checked=action.check_checked(context),
        can_execute=can_execute,
        toolbar_view=toolbar_view,
        menu_view=menu_view,
        menu_refs=menu_refs,
        menu_placement=action.menu_placement,
    )


def _infer_variant(
    *,
    action: Action,
    ref: ActionRef,
    context: ActionContext,
    toolbar_view: View | None,
    menu_view: View | None,
    menu_refs: list[ActionRef],
    can_execute: bool,
) -> ActionVariant:
    variant = ref.variant or action.variant
    if variant != "auto":
        return variant

    if context.surface == "menu":
        return "button"

    has_menu = menu_view is not None or bool(menu_refs)
    if toolbar_view is not None:
        return "widget"
    if has_menu and can_execute:
        return "split"
    if has_menu:
        return "dropdown"
    return "button"


def _resolve_placement(
    *,
    action: Action,
    ref: ActionRef,
) -> ParsedPlacement:
    if ref.placement is not None:
        return _parse_placement(ref.placement)
    if ref.order is not None:
        return _parse_placement(ref.order)
    if action.placement:
        return _parse_placement(action.placement)
    return _parse_placement(action.order)


def _dedupe_resolved(
    items: list[ResolvedAction],
) -> list[ResolvedAction]:
    deduped: list[ResolvedAction] = []
    seen_keys: set[str] = set()
    for item in items:
        if item.key in seen_keys:
            continue
        seen_keys.add(item.key)
        deduped.append(item)
    return deduped


def _action_classes() -> list[type[Action]]:
    classes = [
        sub for sub in mutobj.discover_subclasses(Action)
        if sub is not Action
    ]
    return sorted(classes, key=lambda item: (
        mutobj.field_default(item.order) or 0,
        item.__module__,
        item.__qualname__,
    ))


def _provider_classes() -> list[type[ActionCategoryProvider]]:
    classes = [
        sub for sub in mutobj.discover_subclasses(ActionCategoryProvider)
        if sub is not ActionCategoryProvider
    ]
    return sorted(classes, key=lambda item: (
        mutobj.field_default(item.order),
        item.__module__,
        item.__qualname__,
    ))


def _instantiate_action(source: ActionSource | None) -> Action:
    if source is None:
        raise ValueError("ActionRef.action 不能为空")
    if isinstance(source, Action):
        return source
    if isinstance(source, str):
        action_cls = mutobj.resolve_class(source, base_cls=Action)
        return action_cls()
    return source()
