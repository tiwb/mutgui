"""事件系统 — Event + EventHandler 家族。

EventHandler / Callback / Bind / MenuTrigger 构成事件处理策略层次，
所有事件参数都是 ``Expr`` 抽象（见 ``mutgui.expr`` 模块）。

参见 `docs/specifications/refactor-callback-explicit-expr.md`。
"""

from __future__ import annotations

from dataclasses import dataclass, field, KW_ONLY
from typing import Any, Callable, TYPE_CHECKING, Mapping, Sequence

import mutobj

if TYPE_CHECKING:
    from .view import View, WireValue, WireNode
    from .expr import Expr


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Event:
    """运行时事件 — 纯数据，不含处理逻辑。"""

    component_id: str
    name: str
    args: Sequence["WireValue"] = field(default_factory=list["WireValue"])
    kwargs: Mapping[str, "WireValue"] = field(default_factory=dict[str, "WireValue"])
    _: KW_ONLY
    handler_id: int = -1
    viewport_id: int | None = None


# ---------------------------------------------------------------------------
# EventHandler 基类
# ---------------------------------------------------------------------------

class EventHandler(mutobj.Declaration):
    """事件处理策略 — 声明在 render 中，定义提取和处理方式。

    基类直接使用时：只提取数据、不消费（事件 fall through 到 ``View.on_event``）。
    子类 ``Callback`` / ``Bind`` / ``MenuTrigger`` 覆盖 ``handle()`` 添加消费行为。

    关键字参数接受任意类型：
        - 普通值（str / int / View 实例 ...）→ 自动包装为 direct，dispatch 时原样 forward
        - ``Expr.wire(...)`` → wire 环境，对端 resolve
        - ``Expr.host(...)`` → host 环境，本端 walk
    """
    args: "tuple[Expr, ...]"
    kwargs: "dict[str, Expr]"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...

    async def handle(self, view: "View", event: Event) -> bool:
        """处理事件。返回 True 表示已消费。基类不消费。"""
        ...

    def to_wire(self, handler_id: int) -> WireNode:
        """只把 wire 环境的参数写入 wire payload。"""
        ...


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class Callback(EventHandler):
    """提取数据 → callback(*args, **kwargs)。不自动 invalidate。"""
    callback: "Callable[..., Any]"

    def __init__(
        self,
        callback: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """声明一个事件回调。

        语义类比 ``functools.partial``：构造期记录的 positional / keyword 参数，
        在事件 dispatch 时按顺序、按名字映射到 ``callback`` 的形参。区别在于
        每个参数都是**延迟求值的 binding**，按求值环境（env）分三种：

        - **direct** — 普通 Python 值（view 实例、字面量、render 期变量等），
          原样 forward。任何非 ``Expr`` 值自动归为 direct。
        - **wire** — ``Expr.wire("$N.path")``，由 wire 端事件 payload 提供。
          ``$N`` 是事件参数序号，例如 antd Menu 的 onClick 第 0 个参数是
          ``{key, keyPath, item, domEvent}``，则 ``Expr.wire("$0.key")`` 抽 ``key``。
        - **host** — ``Expr.host("event.path")``，由本端 dispatch context 求值。

        位置参数和关键字参数都按 env 分派，可任意混用。
        **字符串就是字符串**——想触发 wire 端 resolvePath 必须显式 ``Expr.wire(...)``。

        示例::

            Callback(self._on_click)                                              # 无参
            Callback(self._on_click, self, "primary", key, count=42)              # direct: view / 字面量 / render 期变量（keyword 等价：view=self）
            Callback(self._on_menu_click, self, Expr.wire("$0.key"))              # view + wire 混合（antd Menu 高频）
            Callback(self._on_change, value=Expr.wire("$0.target.value"))         # wire keyword
            Callback(self._on_click, viewport_id=Expr.host("event.viewport_id"))  # host keyword
            Callback(self._on_drag, Expr.wire("$0.x"), Expr.wire("$0.y"))         # 多个 wire 位置参数
        """
        ...

    async def handle(self, view: "View", event: Event) -> bool:
        ...


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------

class Bind(EventHandler):
    """提取 wire 端的值赋给后端属性 → setattr(obj, attr, value) + invalidate。

    ``path`` 语义已锁定为 wire 表达式，所以接受字符串简写：

        Bind(self, "name", "$0.target.value")           # 字符串简写
        Bind(self, "name", Expr.wire("$0.target.value")) # 等价显式
        Bind(self, "value", "$0")                        # 默认 onChange(val) 形式

    其他类型一律 ``TypeError``。要赋常量请直接 setattr 或用 Callback + lambda。
    """
    path_expr: "Expr"
    obj: Any
    attr: str

    def __init__(
        self,
        obj: Any,
        attr: str,
        path: "str | Expr" = "$0",
    ) -> None:
        ...

    async def handle(self, view: "View", event: Event) -> bool:
        ...

    def to_wire(self, handler_id: int) -> WireNode:
        ...


# ---------------------------------------------------------------------------
# EventFilter
# ---------------------------------------------------------------------------

class EventFilter:
    """事件观察/拦截器。"""

    async def on_event_filter(self, watched: "View", event: Event) -> bool:
        """返回 True 吞掉事件，target 的 on_event 不会被调用。"""
        return False


from . import _events_impl as _events_impl  # noqa: F401, E402
