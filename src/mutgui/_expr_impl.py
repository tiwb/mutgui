"""Expr 实现细节 — parse/eval host expr、coerce、wire/host classmethod 赋值。"""

from __future__ import annotations

import ast
import functools
import re
from typing import Any

from .expr import Expr


# 单段：('name', str) | ('attr', str) | ('index', int)
HostSeg = tuple[str, Any]

# wire expr 必须以 $N（N 非负整数）开头，后续语法由对端 resolver 定义
_WIRE_PREFIX_RE = re.compile(r"^\$(\d+)")


def expr_wire(cls: type[Expr], source: str) -> Expr:
    """声明从 wire 端 payload 取值的引用。

    语法：``$N`` 入口（N 是事件参数序号） + 点分属性链 + ``[int]`` 下标。
    构造期只校验 ``$N`` 前缀，详细语法由对端 resolver 定义。
    """
    if not isinstance(source, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(
            f"Expr.wire source must be str, got {type(source).__name__}"
        )
    if not _WIRE_PREFIX_RE.match(source):
        raise ValueError(
            f"Wire expr must start with $N (event arg index): {source!r}"
        )
    return cls(env="wire", source=source)


def expr_host(cls: type[Expr], source: str) -> Expr:
    """声明从 host 端 dispatch context 取值的引用。

    语法：Name 入口 + ``.attr`` + ``[int]`` 下标，AST 严格白名单。
    构造期完整解析，错误立即抛 ``ValueError``。
    """
    if not isinstance(source, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(
            f"Expr.host source must be str, got {type(source).__name__}"
        )
    # 构造期解析 → 立即暴露错误（结果丢弃，求值期重新走缓存）
    parse_host_expr(source)
    return cls(env="host", source=source)


# 模块加载时替换 Expr 类方法
Expr.wire = classmethod(expr_wire)  # pyright: ignore[reportAttributeAccessIssue]
Expr.host = classmethod(expr_host)  # pyright: ignore[reportAttributeAccessIssue]


def coerce_expr(value: Any) -> Expr:
    """非 Expr 值视作 direct 环境的 source，自动包装。"""
    if isinstance(value, Expr):
        return value
    return Expr(env="direct", source=value)


@functools.lru_cache(maxsize=512)
def parse_host_expr(source: str) -> tuple[HostSeg, ...]:
    """把 host expr 解析成段列表。

    白名单语法：``Name`` + ``Attribute`` + ``Subscript[int]``。
    其他形态（dict key、负数下标、算术、调用等）一律拒绝。
    """
    try:
        tree: ast.expr = ast.parse(source, mode="eval").body
    except SyntaxError as exc:
        raise ValueError(f"Invalid host expr: {source!r}") from exc

    segs: list[HostSeg] = []
    while isinstance(tree, (ast.Attribute, ast.Subscript)):
        if isinstance(tree, ast.Attribute):
            segs.append(("attr", tree.attr))
            tree = tree.value
        else:
            slc = tree.slice
            # 拒绝 bool（True/False 是 Constant 的子类，但 isinstance(True, int) == True）
            if not (
                isinstance(slc, ast.Constant)
                and isinstance(slc.value, int)
                and not isinstance(slc.value, bool)
            ):
                raise ValueError(
                    f"Only integer index supported in host expr: {source!r}"
                )
            segs.append(("index", slc.value))
            tree = tree.value
    if not isinstance(tree, ast.Name):
        raise ValueError(f"Host expr must start with a name: {source!r}")
    segs.append(("name", tree.id))
    segs.reverse()
    return tuple(segs)


def eval_host_expr(source: str, context: dict[str, Any]) -> Any:
    """按 context 求值 host expr。命中 ``parse_host_expr`` 缓存。"""
    segs = parse_host_expr(source)
    # 第一段必为 ('name', root)
    kind, name = segs[0]
    assert kind == "name"
    if name not in context:
        raise NameError(
            f"Host expr {source!r} references unknown name {name!r}; "
            f"available: {sorted(context)}"
        )
    val: Any = context[name]
    for kind, key in segs[1:]:
        if kind == "attr":
            val = getattr(val, key)
        else:  # index
            val = val[key]
    return val
