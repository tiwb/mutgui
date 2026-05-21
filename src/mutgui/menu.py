"""菜单系统 — MenuView + MenuTrigger。

MenuView 是渲染在 portal 浮层中的 View，按需创建、关闭销毁。
MenuTrigger 是 EventHandler 子类，声明"此事件弹出菜单"。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Literal, TYPE_CHECKING

import mutobj

from .events import EventHandler
from .view import View, WireNode

if TYPE_CHECKING:
    from .events import Event


MenuPlacement = Literal[
    "cursor",
    "top-start",
    "top-center",
    "top-end",
    "bottom-start",
    "bottom-center",
    "bottom-end",
    "left-start",
    "left-end",
    "right-start",
    "right-end",
]


class MenuView(View):
    """菜单 View — render() 输出菜单内容。

    按需创建，关闭时销毁。每次触发创建独立实例，
    自然解决 per-viewport 问题。
    """

    id: str | int = mutobj.field(default_factory=lambda: f"$menu:{uuid.uuid4().hex[:8]}")
    origin_channel_id: int | None = None  # 触发 viewport 的 channel_id（per-viewport 作用域过滤）

    async def close(self) -> None:
        """关闭菜单 — 从宿主 View 移除自身。

        宿主（lifecycle host）由 `_menu_impl.MenuRuntime` Extension 内部维护，
        业务代码无需感知。
        """
        ...


class MenuTrigger(EventHandler):
    """菜单触发器 — 声明"此事件弹出菜单"。

    复用 $handler + resolvePath 机制，通过 $menu key 标识身份。
    前端看到 $menu → 走菜单逻辑（记住坐标、发 context、等 push、渲染）。
    """
    menu_factory: "Callable[..., MenuView]"
    placement: MenuPlacement

    def __init__(
        self,
        menu_factory: Callable[..., MenuView],
        /,
        *args: Any,
        placement: MenuPlacement = "cursor",
        **kwargs: Any,
    ) -> None:
        """参数语义与 `Callback` 对称，dispatch 时 ``menu_factory(*args, **kwargs)``。

        Args:
            menu_factory: 接收 positional + keyword 参数，返回 MenuView 实例。
                broker/client 侧须 import 的 View 才能被模块系统发现。
            *args: positional 参数。非 `Expr` 值自动归为 direct。
            placement: 定位策略，见 ``MenuPlacement`` 定义。
            **kwargs: 按 Expr 环境分派：
                - 普通值（如 ``panel=self``）→ direct，透传给 menu_factory
                - ``Expr.wire(...)`` → 由前端 resolve 后送入
                - ``Expr.host(...)`` → 本端按 dispatch context 求值
        """
        ...

    async def handle(self, view: View, event: Event) -> bool:
        """创建 MenuView 并挂载到宿主 View。"""
        ...

    def to_wire(self) -> WireNode:
        ...


from . import _menu_impl as _menu_impl  # noqa: F401, E402
