"""事件 helper — notify / handler / bind。

在后端 schema 的 onXXX 位置使用，显式声明前端事件的数据提取规则。
"""

from __future__ import annotations

from typing import Any, Callable

# 标记 key，用于区分框架构造和普通数据
TAG_KEY = "$"


def notify(**extract: str) -> dict[str, Any]:
    """提取数据，发送到 view.on_event()。

    用法::

        {"onChange": notify(value="$0.target.value")}

    前端触发 onChange 时，从回调参数提取 value，发送事件到后端。
    后端通过 view.on_event() 接收。
    """
    return {TAG_KEY: "handler", "extract": extract}


def handler(fn: Callable[..., Any], **extract: str) -> dict[str, Any]:
    """提取数据，调用指定方法。

    用法::

        {"onClick": handler(self.save)}
        {"onChange": handler(self.on_name, value="$0.target.value")}

    前端触发事件时，提取数据并直接调用 fn(data)。
    """
    return {TAG_KEY: "handler", "fn": fn, "extract": extract}


def bind(obj: Any, attr: str, path: str = "$0") -> dict[str, Any]:
    """提取数据，自动写回对象属性。

    用法::

        {"onChange": bind(self, "name", "$0.target.value")}
        {"onChange": bind(self, "age", "$0")}

    前端触发事件时，提取值并执行 setattr(obj, attr, value)。
    """
    return {TAG_KEY: "bind", "obj": obj, "attr": attr, "path": path}
