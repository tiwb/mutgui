"""Action system — 高于 Menu 的可扩展动作抽象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias, TYPE_CHECKING

import mutobj

from .menu import MenuPlacement, MenuView
from .view import View, ViewBlock

if TYPE_CHECKING:
    ActionSource: TypeAlias = str | type["Action"] | "Action"
else:
    ActionSource = Any


ActionSurface = Literal["toolbar", "menu", "dock"]
ActionPosition = Literal["start", "end"]
ActionVariant = Literal["auto", "button", "widget", "dropdown", "split"]
ToolbarLabelMode = Literal["auto", "always", "icon-only"]


@dataclass(slots=True)
class ActionContext:
    surface: ActionSurface = "toolbar"
    category: str | None = None
    data: dict[str, Any] = field(default_factory=dict[str, Any])

    def with_updates(
        self,
        *,
        surface: ActionSurface | None = None,
        category: str | None = None,
        **updates: Any,
    ) -> "ActionContext":
        data = dict(self.data)
        data.update(updates)
        return ActionContext(
            surface=self.surface if surface is None else surface,
            category=self.category if category is None else category,
            data=data,
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


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


class Action(mutobj.Declaration):
    """可被不同 surface 复用的动作项。

    子类只需声明 `action_id` 和 `categories` 等字段，重写 `execute()`。
    其余钩子（visible / enabled / checked / toolbar_view / menu_view）
    按需覆盖，不覆盖即为默认行为。
    """

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
    menu_placement: MenuPlacement = "bottom-start"

    def resolved_action_id(self) -> str:
        """动作唯一标识。优先取 `action_id`，未设时回退到类全路径。

        ``action_id`` 是最简洁的标识；如果类自身已经足以区分，
        可以不设 ``action_id``，此方法自动推导。
        """
        ...

    def resolved_label(self, context: ActionContext | None = None) -> str:
        """动作在 UI 中的显示文本。优先取 `label`，为空时回退到 `resolved_action_id()`。"""
        ...

    def check_visible(self, context: ActionContext) -> bool:
        """Context 感知可见性。返回 False 时该动作不在任何 surface 中显示。"""
        ...

    def check_enabled(self, context: ActionContext) -> bool:
        """Context 感知可用性。返回 False 时灰显禁用。"""
        ...

    def check_checked(self, context: ActionContext) -> bool:
        """Context 感知选中态。返回 True 时高亮。"""
        ...

    def execute(self, context: ActionContext) -> None:
        """动作主入口。子类必须重写。 """
        ...

    def toolbar_view(self, context: ActionContext) -> View | None:
        """在 toolbar 按钮旁内联渲染的自定义组件。

        返回非 None 时，toolbar 会将该 View 作为 widget 嵌入按钮右侧。
        常用于进度条、徽章等内联 UI。
        """
        ...

    def menu_actions(self, context: ActionContext) -> list[ActionRef]:
        """返回下拉菜单的子项列表。解析器据此构建子菜单。"""
        ...

    def menu_view(self, context: ActionContext) -> View | None:
        """在菜单项旁内联渲染的自定义组件。

        返回非 None 时，菜单会将该 View 作为菜单项内联嵌入。
        """
        ...


class ActionCategoryProvider(mutobj.Declaration):
    """按 category 动态展开动作引用。

    当 ActionToolbar / ActionMenu 指定 category 字符串时，
    解析器通过匹配的 Provider 将 category 展开为具体 ActionRef 列表。
    """

    categories: tuple[str, ...] = ()
    order: int = 0

    def refs(self, context: ActionContext) -> list[ActionRef]:
        """返回该 category 对应的 ActionRef 列表。"""
        ...



class ActionMenu(MenuView):
    """基于 category / ActionRef 渲染的高层菜单。

    支持三种入口：
    - 直接指定 ``refs`` 和 ``categories``
    - 通过 ``source_action`` 从某个 Action 继承子菜单
    """

    categories: list[str] = mutobj.field(default_factory=list)
    refs: list[ActionRef] = mutobj.field(default_factory=list)
    context: ActionContext | None = None
    source_action: Action | None = None
    empty_label: str = "暂无可用动作"

    def render(self) -> ViewBlock:
        """解析 refs + categories 并产出菜单组件。"""
        ...


class ActionToolbar(View):
    """基于 category / ActionRef 渲染的高层 toolbar。

    自动按 ``position`` 将动作分为 start / end 两组，
    按 placement 排序，在不同 group 间插入分隔线。
    """

    categories: list[str] = mutobj.field(default_factory=list)
    refs: list[ActionRef] = mutobj.field(default_factory=list)
    context: ActionContext | None = None
    gap: int = 6
    wrap: bool = True
    label_mode: ToolbarLabelMode = "auto"

    def render(self) -> ViewBlock:
        """解析 refs + categories 并产出 toolbar 组件。"""
        ...


from . import _action_impl as _action_impl  # noqa: E402, F401
