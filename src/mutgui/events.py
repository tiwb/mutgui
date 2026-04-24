"""事件系统 — Event + EventHandler。

Event 纯数据，描述"发生了什么"。
EventHandler 策略对象，定义"怎么处理"。
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .view import View


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


class EventHandler:
    """事件处理策略 — 声明在 render 中，定义提取和处理方式。

    直接使用时：只提取数据，不消费（等同旧 Notify）。
    子类 Callback/Bind 覆盖 handle() 添加消费行为。
    """

    def __init__(self, **extract: str) -> None:
        super().__init__()
        self.extract = extract

    async def handle(self, view: View, event: Event) -> bool:
        """处理事件。返回 True 表示已消费。基类不消费。"""
        return False

    def to_wire(self) -> dict[str, Any]:
        return {"$handler": dict(self.extract)}


class Callback(EventHandler):
    """提取数据 -> callback(*args, **kwargs)。不自动 invalidate。

    位置参数 (*args) 和关键字参数 (**extract) 是 **前端 resolvePath 提取路径**：

        Callback(handler, "$0.target.value")   # event.target.value 作为第一个参数
        Callback(handler, x="$0.x", y="$0.y")  # event.x / event.y 作为关键字参数
        Callback(handler, "$0", "$1")          # 第一个和第二个事件参数（onChange(val, opt) 这类）

    `@` 前缀路径在后端注入，不进入 wire（如 `view="@view"`、`session="@view.session"`）。

    传后端常量（与事件无关的固定值）请用 `functools.partial` 或 `lambda`：

        Callback(partial(handler, "Python Script"))
        Callback(lambda val=item.id: handler(val))    # for 循环里用默认参数捕获

    **不要写** `Callback(handler, "Python Script")` — 字符串会被当作前端 resolvePath
    路径表达式，运行时只能解析出 None。这是预期行为，给未来更复杂的提取语法
    （方法调用、表达式、模板等）保留语义空间。
    """

    def __init__(self, callback: Callable[..., Any], /, *args: str, **extract: str) -> None:
        super().__init__()
        self.callback = callback
        self.args = args
        self.extract = extract

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        kwargs = {k: v for k, v in event.data.items() if k != "$args"}
        # @-prefix: 后端注入（@event.xxx / @view）
        inject_sources = {"event": event, "view": view}
        for k, v in self.extract.items():
            if v.startswith("@"):
                parts = v[1:].split(".")
                obj = inject_sources.get(parts[0])
                for attr in parts[1:]:
                    obj = getattr(obj, attr, None)
                kwargs[k] = obj
        result = self.callback(*args, **kwargs)
        if inspect.isawaitable(result):
            await result
        return True

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, str | list[str]] = {
            k: v for k, v in self.extract.items()
            if not v.startswith("@")
        }
        if self.args:
            wire["$args"] = list(self.args)
        return {"$handler": wire}


class Bind(EventHandler):
    """提取数据 -> setattr(obj, attr, value)。自动 invalidate。

    `path` 参数是 **前端 resolvePath 提取路径**（默认 `"$0"`）。

    常用路径：
        Bind(self, "name", "$0.target.value")     # 原生 <input>
        Bind(self, "checked", "$0.target.checked") # 原生 <checkbox>
        Bind(self, "value", "$0")                  # 组件 onChange 直接给值（如 InputNumber）

    `path` 不接受常量 — 它的语义是"从前端事件提取一个值赋给 attr"，
    要赋常量请直接 setattr 或用 Callback + lambda。
    """

    def __init__(self, obj: Any, attr: str, path: str = "$0") -> None:
        super().__init__()
        self.obj = obj
        self.attr = attr
        self.path = path
        self.extract: dict[str, str] = {}

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        setattr(self.obj, self.attr, args[0] if args else None)
        view.invalidate()
        return True

    def to_wire(self) -> dict[str, Any]:
        return {"$handler": {"$args": [self.path]}}


class EventFilter:
    """事件观察/拦截器。"""

    async def on_event_filter(self, watched: View, event: Event) -> bool:
        """返回 True 吞掉事件，target 的 on_event 不会被调用。"""
        return False
