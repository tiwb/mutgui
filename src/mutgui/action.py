"""Action system — 高于 Menu 的可扩展动作抽象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

import mutobj

from .events import Callback
from .menu import MenuTrigger, MenuView
from .view import View, ViewBlock

if TYPE_CHECKING:
    ActionSource = str | type["Action"] | "Action"
else:
    ActionSource = Any


ActionSurface = Literal["toolbar", "menu", "dock"]
ActionPosition = Literal["start", "end"]
ActionVariant = Literal["auto", "button", "widget", "dropdown", "split"]
ToolbarLabelMode = Literal["auto", "always", "icon-only"]
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
class ActionContext:
    owner: View | None = None
    surface: ActionSurface = "toolbar"
    category: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def with_updates(
        self,
        *,
        owner: View | None = None,
        surface: ActionSurface | None = None,
        category: str | None = None,
        **updates: Any,
    ) -> "ActionContext":
        data = dict(self.data)
        data.update(updates)
        return ActionContext(
            owner=self.owner if owner is None else owner,
            surface=self.surface if surface is None else surface,
            category=self.category if category is None else category,
            data=data,
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def _menu_arrow(placement: str) -> str:
    """根据 placement 返回对应的箭头符号。"""
    side = placement.split("-")[0] if "-" in placement else placement
    return {"top": "▴", "bottom": "▾", "left": "◂", "right": "▸"}.get(side, "▾")


@dataclass(slots=True)
class ActionRef:
    action: ActionSource | None = None
    category: str | None = None
    ref_id: str | None = None
    variant: ActionVariant | None = None
    position: ActionPosition | None = None
    label: str | None = None
    icon: str | None = None
    tooltip: str | None = None
    shortcut: str | None = None
    placement: str | int | None = None
    order: int | None = None

    def __post_init__(self) -> None:
        if (self.action is None) == (self.category is None):
            raise ValueError("ActionRef 必须且只能指定 action 或 category 其一")


@dataclass(slots=True)
class ResolvedAction:
    key: str
    ref_id: str
    action_id: str
    action: "Action"
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
    menu_placement: str


class Action(mutobj.Declaration):
    """可被不同 surface 复用的动作项。"""

    action_id: str = ""
    categories: tuple[str, ...] = ()
    label: str = ""
    icon: str | None = None
    tooltip: str | None = None
    shortcut: str | None = None
    position: ActionPosition = "end"
    placement: str = ""
    order: int | None = None
    variant: ActionVariant = "auto"
    menu_placement: str = "bottom-start"

    def resolved_action_id(self) -> str:
        if self.action_id:
            return self.action_id
        cls = type(self)
        return f"{cls.__module__}.{cls.__qualname__}"

    def resolved_label(self, context: ActionContext | None = None) -> str:
        return self.label or self.resolved_action_id()

    def check_visible(self, context: ActionContext) -> bool:
        return True

    def check_enabled(self, context: ActionContext) -> bool:
        return True

    def check_checked(self, context: ActionContext) -> bool:
        return False

    def execute(self, context: ActionContext) -> None:
        raise NotImplementedError(f"{type(self).__name__}.execute() 未实现")

    def toolbar_view(self, context: ActionContext) -> View | None:
        return None

    def menu_actions(self, context: ActionContext) -> list[ActionRef]:
        return []

    def menu_view(self, context: ActionContext) -> View | None:
        return None


class ActionCategoryProvider(mutobj.Declaration):
    """按 category 动态展开动作引用。"""

    categories: tuple[str, ...] = ()
    order: int = 0

    def refs(self, context: ActionContext) -> list[ActionRef]:
        return []


class ActionRegistry:
    """动作查询与解析入口。"""

    @classmethod
    def resolve(
        cls,
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
            resolved.extend(cls._expand_category(
                category,
                context=context.with_updates(category=category),
                seen_categories=seen_categories,
            ))
        for ref in refs:
            resolved.extend(cls._expand_ref(ref, context=context,
                                            seen_categories=seen_categories))

        visible = cls._dedupe_resolved([item for item in resolved if item.visible])
        return sorted(visible, key=lambda item: (
            item.group_order,
            item.group_name,
            item.item_order,
        ))

    @classmethod
    def _expand_ref(
        cls,
        ref: ActionRef,
        *,
        context: ActionContext,
        seen_categories: set[str],
    ) -> list[ResolvedAction]:
        if ref.category is not None:
            return cls._expand_category(
                ref.category,
                context=context.with_updates(category=ref.category),
                seen_categories=seen_categories,
            )

        action = cls._instantiate_action(ref.action)
        return [cls._resolve_action(action, ref=ref, context=context)]

    @classmethod
    def _expand_category(
        cls,
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
            for action_cls in cls._action_classes():
                if category in mutobj.field_default(action_cls.categories):
                    refs.append(ActionRef(action=action_cls))
            for provider_cls in cls._provider_classes():
                if category not in mutobj.field_default(provider_cls.categories):
                    continue
                provider = provider_cls()
                refs.extend(provider.refs(context))

            resolved: list[ResolvedAction] = []
            for ref in refs:
                resolved.extend(cls._expand_ref(
                    ref,
                    context=context.with_updates(category=category),
                    seen_categories=seen_categories,
                ))
            return resolved
        finally:
            seen_categories.remove(category)

    @classmethod
    def _resolve_action(
        cls,
        action: "Action",
        *,
        ref: ActionRef,
        context: ActionContext,
    ) -> ResolvedAction:
        action_id = action.resolved_action_id()
        ref_id = ref.ref_id or action_id
        parsed_placement = cls._resolve_placement(action=action, ref=ref)
        toolbar_view = action.toolbar_view(context.with_updates(surface="toolbar"))
        menu_view = action.menu_view(context.with_updates(surface="menu"))
        menu_refs = action.menu_actions(context.with_updates(surface="menu"))
        can_execute = mutobj.impl_has(type(action).execute)
        variant = cls._infer_variant(
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

    @classmethod
    def _infer_variant(
        cls,
        *,
        action: "Action",
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

    @classmethod
    def _resolve_placement(
        cls,
        *,
        action: "Action",
        ref: ActionRef,
    ) -> ParsedPlacement:
        if ref.placement is not None:
            return _parse_placement(ref.placement)
        if ref.order is not None:
            return _parse_placement(ref.order)
        if action.placement:
            return _parse_placement(action.placement)
        return _parse_placement(action.order)

    @classmethod
    def _dedupe_resolved(
        cls,
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

    @classmethod
    def _action_classes(cls) -> list[type["Action"]]:
        classes = [
            sub for sub in mutobj.discover_subclasses(Action)
            if sub is not Action
        ]
        return sorted(classes, key=lambda item: (
            mutobj.field_default(item.order) or 0,
            item.__module__,
            item.__qualname__,
        ))

    @classmethod
    def _provider_classes(cls) -> list[type["ActionCategoryProvider"]]:
        classes = [
            sub for sub in mutobj.discover_subclasses(ActionCategoryProvider)
            if sub is not ActionCategoryProvider
        ]
        return sorted(classes, key=lambda item: (
            mutobj.field_default(item.order),
            item.__module__,
            item.__qualname__,
        ))

    @classmethod
    def _instantiate_action(cls, source: ActionSource | None) -> "Action":
        if source is None:
            raise ValueError("ActionRef.action 不能为空")
        if isinstance(source, Action):
            return source
        if isinstance(source, str):
            action_cls = mutobj.resolve_class(source, base_cls=Action)
            return action_cls()
        if isinstance(source, type) and issubclass(source, Action):
            return source()
        raise TypeError(f"unsupported action source: {source!r}")


class ActionMenu(MenuView):
    """基于 category / ActionRef 渲染的高层菜单。"""

    categories: list[str] = mutobj.field(default_factory=list)
    refs: list[ActionRef] = mutobj.field(default_factory=list)
    context: ActionContext | None = None
    source_action: Action | None = None
    empty_label: str = "暂无可用动作"

    def render(self) -> ViewBlock:
        context = self._base_context().with_updates(surface="menu")
        items: list[dict[str, Any] | View] = []

        if self.source_action is not None:
            items.extend(self._render_source_action(self.source_action, context))

        resolved = ActionRegistry.resolve(
            context=context,
            refs=self.refs,
            categories=self.categories,
        )
        if items and resolved:
            items.append({"$component": "mutgui.Menu.Divider"})
        items.extend(self._render_resolved_items(resolved, context))

        if not items:
            items.append({
                "$component": "mutgui.Menu.Item",
                "$id": "empty",
                "label": self.empty_label,
                "disabled": True,
            })
        return ViewBlock(items)

    def _render_source_action(
        self,
        action: Action,
        context: ActionContext,
    ) -> list[dict[str, Any] | View]:
        items: list[dict[str, Any] | View] = []
        menu_view = action.menu_view(context)
        menu_refs = action.menu_actions(context)
        if menu_view is not None:
            items.append(self._ensure_view_id(menu_view, "menu-view"))
        if menu_view is not None and menu_refs:
            items.append({"$component": "mutgui.Menu.Divider"})
        if menu_refs:
            resolved = ActionRegistry.resolve(context=context, refs=menu_refs)
            items.extend(self._render_resolved_items(resolved, context))
        return items

    def _render_resolved_items(
        self,
        items: list[ResolvedAction],
        context: ActionContext,
    ) -> list[dict[str, Any] | View]:
        rendered: list[dict[str, Any] | View] = []
        prev_group_name: str | None = None
        for index, item in enumerate(items):
            if rendered and item.group_name != prev_group_name:
                rendered.append({"$component": "mutgui.Menu.Divider"})
            if self._should_inline_menu_view(item):
                rendered.append(self._ensure_view_id(
                    item.menu_view,
                    f"menu-view-{item.ref_id}-{index}",
                ))
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

    def _should_inline_menu_view(self, item: ResolvedAction) -> bool:
        return item.menu_view is not None and item.toolbar_view is not None

    def _base_context(self) -> ActionContext:
        if self.context is not None:
            return self.context
        return ActionContext(owner=self.owner, surface="menu")

    def _ensure_view_id(self, view: View, suffix: str) -> View:
        if not view.id:
            base = str(self.id or "action-menu")
            if base.startswith("$menu:"):
                base = f"action-view:{base[6:]}"
            view.id = f"{base}:{suffix}"
        return view


class ActionToolbar(View):
    """基于 category / ActionRef 渲染的高层 toolbar。"""

    def __init__(
        self,
        *,
        id: str,
        categories: list[str] | None = None,
        refs: list[ActionRef] | None = None,
        context: ActionContext | None = None,
        gap: int = 6,
        wrap: bool = True,
        label_mode: ToolbarLabelMode = "auto",
    ) -> None:
        super().__init__()
        self.id = id
        self.categories = categories or []
        self.refs = refs or []
        self.context = context
        self.gap = gap
        self.wrap = wrap
        self.label_mode = label_mode

    def render(self) -> ViewBlock:
        context = self._base_context().with_updates(surface="toolbar")
        actions = ActionRegistry.resolve(
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
                        *self._render_action_strip(start_actions, context, start_index=0),
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
                        *self._render_action_strip(
                            end_actions,
                            context,
                            start_index=len(start_actions),
                        ),
                    ],
                },
            ],
        }])

    def _render_action_strip(
        self,
        actions: list[ResolvedAction],
        context: ActionContext,
        *,
        start_index: int,
    ) -> list[dict[str, Any]]:
        rendered: list[dict[str, Any]] = []
        prev_group_name: str | None = None
        for offset, item in enumerate(actions, start=start_index):
            if rendered and item.group_name != prev_group_name:
                rendered.append(self._group_separator(offset))
            rendered.append(self._render_action(item, context, offset))
            prev_group_name = item.group_name
        return rendered

    def _render_action(
        self,
        item: ResolvedAction,
        context: ActionContext,
        index: int,
    ) -> dict[str, Any]:
        if item.variant == "widget" and item.toolbar_view is not None:
            widget = self._ensure_view_id(
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
                    self._button_schema(
                        item,
                        component_id=f"main-{index}",
                        on_click=(Callback(item.action.execute, context)
                                  if item.can_execute and item.enabled else None),
                        left_rounded=True,
                        right_rounded=False,
                    ),
                    self._button_schema(
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
            return self._button_schema(
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

        return self._button_schema(
            item,
            component_id=f"button-{index}",
            on_click=(Callback(item.action.execute, context)
                      if item.can_execute and item.enabled else None),
        )

    def _button_schema(
        self,
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
        children = self._button_children(
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
            "title": self._button_title(item),
            "disabled": (not item.enabled) if disabled is None else disabled,
            "style": style,
        }
        if on_click is not None:
            node["onClick"] = on_click
        if children is not None:
            if isinstance(children, list):
                node["$children"] = children
            else:
                node["children"] = children
        return node

    def _button_children(
        self,
        icon: str | None,
        label: str,
        *,
        show_menu_arrow: bool = False,
        menu_arrow: str = "▾",
    ) -> list[dict[str, Any]] | str:
        mode = self._effective_label_mode()
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
            children.append({"$component": "span", "$id": "arrow", "children": menu_arrow})
        return children

    def _button_title(self, item: ResolvedAction) -> str:
        title = item.tooltip or item.label
        if item.shortcut:
            return f"{title} ({item.shortcut})"
        return title

    def _effective_label_mode(self) -> Literal["always", "icon-only"]:
        if self.label_mode == "icon-only":
            return "icon-only"
        return "always"

    def _group_separator(self, index: int) -> dict[str, Any]:
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

    def _base_context(self) -> ActionContext:
        if self.context is not None:
            return self.context
        return ActionContext(owner=self, surface="toolbar")

    def _ensure_view_id(self, view: View, suffix: str) -> View:
        if not view.id:
            base = str(self.id or "action-toolbar")
            view.id = f"{base}:{suffix}"
        return view
