"""Expr — 统一三种求值环境的延迟引用。

Expr 是 mutgui 事件系统的"值来源"抽象。每个事件参数都是一条 Expr，
区别仅在于值从哪求（求值环境 env）：

- direct: 构造时已知的 Python 值，dispatch 时原样 forward
- wire:   wire 协议另一端 resolve 出的事件 payload 值
- host:   本端 dispatch context 上按表达式 walk

参见 `docs/specifications/refactor-callback-explicit-expr.md`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ExprEnv = Literal["direct", "wire", "host"]


@dataclass(frozen=True)
class Expr:
    """延迟求值表达式 — dispatch 时按 env 决定求值方式。

    用户不直接构造 ``Expr(...)``，而是用工厂方法：

        Expr.wire("$0.target.value")    # wire 环境
        Expr.host("event.viewport_id")  # host 环境

    direct 环境由 ``Callback`` / ``EventHandler`` 的参数自动包装产生
    （任意非 ``Expr`` 值都视为 direct source）。

    实现细节见 ``_expr_impl.py`` — wire/host 构造验证、parse/eval host expr 等。
    """

    env: ExprEnv
    source: Any

    @classmethod
    def wire(cls, source: str) -> "Expr":
        """声明从 wire 端 payload 取值的引用。实现见 _expr_impl。"""
        ...

    @classmethod
    def host(cls, source: str) -> "Expr":
        """声明从 host 端 dispatch context 取值的引用。实现见 _expr_impl。"""
        ...


from . import _expr_impl as _expr_impl  # noqa: F401, E402
