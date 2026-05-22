"""EventHandler / Callback / Bind Declaration 的默认实现。"""

from __future__ import annotations

import inspect
from typing import Any, Callable, TYPE_CHECKING, Mapping

from mutobj import impl

from .events import (
    Bind,
    Callback,
    Event,
    EventHandler,
)
from .expr import Expr
from ._expr_impl import (
    coerce_expr,
    eval_host_expr,
)

if TYPE_CHECKING:
    from .view import View, WireValue, WireNode


# ---------------------------------------------------------------------------
# 内部辅助 — dispatch context 构造与 keyword 求值
# ---------------------------------------------------------------------------


def _build_dispatch_context(view: View, event: Event) -> dict[str, Any]:
    """构造 host expr 的求值 context。第一版只暴露 ``event``。

    保留 ``view`` 留作未来扩展（如 ``Expr.host("view.session.id")``），
    但显式 review 后再开放——目前不写入 context，避免误用。
    """
    return {"event": event}


def _eval_kwargs(
    kwargs: dict[str, Expr],
    event_kwargs: Mapping[str, WireValue],
    context: dict[str, Any],
) -> dict[str, Any]:
    """按 env 分派求值 keyword 参数。"""
    result: dict[str, Any] = {}
    for k, expr in kwargs.items():
        if expr.env == "direct":
            result[k] = expr.source
        elif expr.env == "wire":
            result[k] = event_kwargs.get(k)
        else:  # host
            result[k] = eval_host_expr(expr.source, context)
    return result


# ---------------------------------------------------------------------------
# EventHandler
# ---------------------------------------------------------------------------


@impl(EventHandler.__init__)
def event_handler_init(self: EventHandler, *args: Any, **kwargs: Any) -> None:
    super(EventHandler, self).__init__()
    self.args = tuple(coerce_expr(a) for a in args)
    self.kwargs = {
        k: coerce_expr(v) for k, v in kwargs.items()
    }


@impl(EventHandler.handle)
async def event_handler_handle(self: EventHandler, view: View, event: Event) -> bool:
    """处理事件。返回 True 表示已消费。基类不消费。"""
    return False


def event_handler_resolve_call(
    self: EventHandler, view: View, event: Event,
) -> tuple[list[Any], dict[str, Any]]:
    """按 env 求值 args/kwargs，返回 (positional, keyword)。

    子类 ``Callback`` / ``MenuTrigger`` 在 ``handle`` 中调用，
    将生成的 positional / keyword 参数 forward 给各自的可调用对象。
    """
    context = _build_dispatch_context(view, event)
    wire_args_payload = event.args
    positional: list[Any] = []
    wire_idx = 0
    for expr in self.args:
        if expr.env == "direct":
            positional.append(expr.source)
        elif expr.env == "wire":
            positional.append(
                wire_args_payload[wire_idx]
                if wire_idx < len(wire_args_payload) else None
            )
            wire_idx += 1
        else:  # host
            positional.append(eval_host_expr(expr.source, context))
    keyword = _eval_kwargs(self.kwargs, event.kwargs, context)
    return positional, keyword


@impl(EventHandler.to_wire)
def event_handler_to_wire(self: EventHandler, handler_id: int) -> WireNode:
    wire: WireNode = {"$handler": handler_id}
    wire_keyword: dict[str, WireValue] = {
        k: e.source for k, e in self.kwargs.items() if e.env == "wire"
    }
    wire_positional = [e.source for e in self.args if e.env == "wire"]
    if wire_positional:
        wire["args"] = wire_positional
    if wire_keyword:
        wire["kwargs"] = wire_keyword
    return wire


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


@impl(Callback.__init__)
def callback_init(
    self: Callback,
    callback: Callable[..., Any],  # pyright: ignore[reportMissingParameterType]
    /,
    *args: Any,
    **kwargs: Any,
) -> None:
    super(Callback, self).__init__(*args, **kwargs)
    self.callback = callback


@impl(Callback.handle)
async def callback_handle(self: Callback, view: View, event: Event) -> bool:
    positional, keyword = event_handler_resolve_call(self, view, event)
    result = self.callback(*positional, **keyword)
    if inspect.isawaitable(result):
        await result
    return True


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------


@impl(Bind.__init__)
def bind_init(
    self: Bind,
    obj: Any,
    attr: str,
    path: str | Expr = "$0",
) -> None:
    super(Bind, self).__init__()
    if isinstance(path, str):
        self.path_expr = Expr.wire(path)
    else:
        if path.env != "wire":
            raise TypeError(
                f"Bind only accepts wire expr, got env={path.env!r}"
            )
        self.path_expr = path
    self.obj = obj
    self.attr = attr


@impl(Bind.handle)
async def bind_handle(self: Bind, view: View, event: Event) -> bool:
    setattr(self.obj, self.attr, event.args[0] if event.args else None)
    view.invalidate()
    return True


@impl(Bind.to_wire)
def bind_to_wire(self: Bind, handler_id: int) -> WireNode:
    return {"$handler": handler_id, "args": [self.path_expr.source]}
