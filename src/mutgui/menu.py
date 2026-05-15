"""菜单系统 — MenuView + MenuTrigger。

MenuView 是渲染在 portal 浮层中的 View，按需创建、关闭销毁。
MenuTrigger 是 EventHandler 子类，声明"此事件弹出菜单"。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, TYPE_CHECKING

import mutobj

from .events import EventHandler
from .view import View

if TYPE_CHECKING:
    from .events import Event


_VALID_PLACEMENTS = {
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
}


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
        raise NotImplementedError


class MenuTrigger(EventHandler):
    """菜单触发器 — 声明"此事件弹出菜单"。

    复用 $handler + resolvePath 机制，通过 $menu key 标识身份。
    前端看到 $menu → 走菜单逻辑（记住坐标、发 context、等 push、渲染）。

    参数语义与 `Callback` 对称：dispatch 时 `menu_factory(*args, **kwargs)`，
    每个参数按 Expr.env 延迟求值（direct / wire / host）。

    参数:
        menu_factory: 接收 positional + keyword 参数，返回 MenuView 实例
        *args: positional 参数。任意类型；非 `Expr` 值自动归为 direct。
        placement: keyword-only 定位策略：
            'cursor'
            'top-start' | 'top-center' | 'top-end'
            'bottom-start' | 'bottom-center' | 'bottom-end'
            'left-start' | 'left-end'
            'right-start' | 'right-end'
        **kwargs: keyword 参数 — 同 Callback 的 kwargs 语义，按 Expr 环境分派：
            - 普通值（如 `panel=self`）→ direct，透传给 menu_factory
            - `Expr.wire(...)` → 由前端 resolve 后送入
            - `Expr.host(...)` → 本端按 dispatch context 求值
    """

    def __init__(
        self,
        menu_factory: Callable[..., MenuView],
        /,
        *args: Any,
        placement: str = "cursor",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if placement not in _VALID_PLACEMENTS:
            allowed = ", ".join(sorted(_VALID_PLACEMENTS))
            raise ValueError(f"invalid menu placement: {placement!r}; expected one of: {allowed}")
        self.menu_factory = menu_factory
        self.placement = placement

    async def handle(self, view: View, event: Event) -> bool:
        """创建 MenuView 并挂载到宿主 View。"""
        raise NotImplementedError

    def to_wire(self) -> dict[str, Any]:
        wire = super().to_wire()["$handler"]
        wire["$menu"] = True
        if self.placement != "cursor":
            wire["$placement"] = self.placement
        return {"$handler": wire}


from . import _menu_impl as _menu_impl  # noqa: F401, E402
