"""事件系统 — Event + Expr + EventHandler 家族。

设计：所有事件参数都是同一抽象（`Expr`）的不同 binding，
区别在于"值的来源"（求值环境）：

- direct: 构造时已知的 Python 值，dispatch 时直接 forward
- wire:   wire 协议另一端 resolve 出的事件 payload 值
- host:   本端（运行 mutgui 业务代码这一侧）dispatch context 上按表达式 walk

参见 `docs/specifications/refactor-callback-explicit-expr.md`。
"""

from __future__ import annotations

import ast
import functools
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .view import View


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

class Event:
    """运行时事件 — 纯数据，不含处理逻辑。"""

    __slots__ = ("component_id", "name", "data", "viewport_id")

    def __init__(
        self,
        component_id: str,
        name: str,
        data: dict[str, Any],
        *,
        viewport_id: int | None = None,
    ) -> None:
        super().__init__()
        self.component_id = component_id
        self.name = name
        self.data = data
        self.viewport_id = viewport_id


# ---------------------------------------------------------------------------
# Expr — 统一三种求值环境的延迟引用
# ---------------------------------------------------------------------------

ExprEnv = Literal["direct", "wire", "host"]

# wire expr 必须以 $N（N 非负整数）开头，后续语法由对端 resolver 定义
_WIRE_PREFIX_RE = re.compile(r"^\$(\d+)")


@dataclass(frozen=True)
class Expr:
    """延迟求值表达式 — dispatch 时按 env 决定求值方式。

    用户不直接构造 `Expr(...)`，而是用工厂方法：

        Expr.wire("$0.target.value")    # wire 环境
        Expr.host("event.viewport_id")  # host 环境

    direct 环境由 `Callback` / `EventHandler` 的参数自动包装产生
    （任意非 Expr 值都视为 direct source）。
    """

    env: ExprEnv
    source: Any  # direct: 任意 Python 值；wire/host: str

    @classmethod
    def wire(cls, source: str) -> "Expr":
        """声明从 wire 端 payload 取值的引用。

        语法：`$N` 入口（N 是事件参数序号） + 点分属性链 + `[int]` 下标。
        构造期只校验 `$N` 前缀，详细语法由对端 resolver 定义。
        """
        if not isinstance(source, str):
            raise TypeError(
                f"Expr.wire source must be str, got {type(source).__name__}"
            )
        if not _WIRE_PREFIX_RE.match(source):
            raise ValueError(
                f"Wire expr must start with $N (event arg index): {source!r}"
            )
        return cls(env="wire", source=source)

    @classmethod
    def host(cls, source: str) -> "Expr":
        """声明从 host 端 dispatch context 取值的引用。

        语法：Name 入口 + `.attr` + `[int]` 下标，AST 严格白名单。
        构造期完整解析，错误立即抛 `ValueError`。
        """
        if not isinstance(source, str):
            raise TypeError(
                f"Expr.host source must be str, got {type(source).__name__}"
            )
        # 构造期解析 → 立即暴露错误（结果丢弃，求值期重新走缓存）
        parse_host_expr(source)
        return cls(env="host", source=source)


def _coerce_expr(value: Any) -> Expr:
    """非 Expr 值视作 direct 环境的 source，自动包装。"""
    if isinstance(value, Expr):
        return value
    return Expr(env="direct", source=value)


# ---------------------------------------------------------------------------
# Host expr 解析与求值
# ---------------------------------------------------------------------------

# 单段：('name', str) | ('attr', str) | ('index', int)
HostSeg = tuple[str, Any]


@functools.lru_cache(maxsize=512)
def parse_host_expr(source: str) -> tuple[HostSeg, ...]:
    """把 host expr 解析成段列表。

    白名单语法：`Name` + `Attribute` + `Subscript[int]`。
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
    """按 context 求值 host expr。命中 `parse_host_expr` 缓存。"""
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


# ---------------------------------------------------------------------------
# EventHandler 基类
# ---------------------------------------------------------------------------

class EventHandler:
    """事件处理策略 — 声明在 render 中，定义提取和处理方式。

    基类直接使用时：只提取数据、不消费（事件 fall through 到 `View.on_event`）。
    子类 `Callback` / `Bind` / `MenuTrigger` 覆盖 `handle()` 添加消费行为。

    关键字参数接受任意类型：
        - 普通值（str / int / View 实例 ...）→ 自动包装为 direct，dispatch 时原样 forward
        - `Expr.wire(...)` → wire 环境，对端 resolve
        - `Expr.host(...)` → host 环境，本端 walk
    """

    def __init__(self, **extract: Any) -> None:
        super().__init__()
        self.extract: dict[str, Expr] = {
            k: _coerce_expr(v) for k, v in extract.items()
        }

    async def handle(self, view: "View", event: Event) -> bool:
        """处理事件。返回 True 表示已消费。基类不消费。"""
        return False

    def to_wire(self) -> dict[str, Any]:
        """只把 wire 环境的参数写入 wire payload。"""
        return {"$handler": {
            k: e.source for k, e in self.extract.items() if e.env == "wire"
        }}


def _build_dispatch_context(view: "View", event: Event) -> dict[str, Any]:
    """构造 host expr 的求值 context。第一版只暴露 `event`。

    保留 `view` 留作未来扩展（如 `Expr.host("view.session.id")`），
    但显式 review 后再开放——目前不写入 context，避免误用。
    """
    return {"event": event}


def _eval_kwargs(
    extract: dict[str, Expr],
    event_data: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """按 env 分派求值 keyword 参数。"""
    result: dict[str, Any] = {}
    for k, expr in extract.items():
        if expr.env == "direct":
            result[k] = expr.source
        elif expr.env == "wire":
            result[k] = event_data.get(k)
        else:  # host
            result[k] = eval_host_expr(expr.source, context)
    return result


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class Callback(EventHandler):
    """提取数据 → callback(*args, **kwargs)。不自动 invalidate。"""

    def __init__(
        self,
        callback: Callable[..., Any],
        /,
        *args: Any,
        **extract: Any,
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
        super().__init__(**extract)
        self.callback = callback
        self.args: tuple[Expr, ...] = tuple(_coerce_expr(a) for a in args)

    async def handle(self, view: "View", event: Event) -> bool:
        context = _build_dispatch_context(view, event)
        wire_args_payload = event.data.get("$args", [])

        # 位置参数：按 self.args 顺序还原（wire 参数从 payload 顺序取）
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

        keyword = _eval_kwargs(self.extract, event.data, context)

        result = self.callback(*positional, **keyword)
        if inspect.isawaitable(result):
            await result
        return True

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            k: e.source for k, e in self.extract.items() if e.env == "wire"
        }
        wire_positional = [e.source for e in self.args if e.env == "wire"]
        if wire_positional:
            wire["$args"] = wire_positional
        return {"$handler": wire}


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------

class Bind(EventHandler):
    """提取 wire 端的值赋给后端属性 → setattr(obj, attr, value) + invalidate。

    `path` 语义已锁定为 wire 表达式，所以接受字符串简写：

        Bind(self, "name", "$0.target.value")           # 字符串简写
        Bind(self, "name", Expr.wire("$0.target.value")) # 等价显式
        Bind(self, "value", "$0")                        # 默认 onChange(val) 形式

    其他类型一律 `TypeError`。要赋常量请直接 setattr 或用 Callback + lambda。
    """

    def __init__(
        self,
        obj: Any,
        attr: str,
        path: "str | Expr" = "$0",
    ) -> None:
        super().__init__()
        if isinstance(path, str):
            self.path_expr = Expr.wire(path)
        elif isinstance(path, Expr):
            if path.env != "wire":
                raise TypeError(
                    f"Bind only accepts wire expr, got env={path.env!r}"
                )
            self.path_expr = path
        else:
            raise TypeError(
                f"Bind path must be str or Expr.wire, "
                f"got {type(path).__name__}"
            )
        self.obj = obj
        self.attr = attr

    async def handle(self, view: "View", event: Event) -> bool:
        args = event.data.get("$args", [])
        setattr(self.obj, self.attr, args[0] if args else None)
        view.invalidate()
        return True

    def to_wire(self) -> dict[str, Any]:
        return {"$handler": {"$args": [self.path_expr.source]}}


# ---------------------------------------------------------------------------
# EventFilter
# ---------------------------------------------------------------------------

class EventFilter:
    """事件观察/拦截器。"""

    async def on_event_filter(self, watched: "View", event: Event) -> bool:
        """返回 True 吞掉事件，target 的 on_event 不会被调用。"""
        return False
