"""ViewSession — 管理 View 的 render→serialize→send 循环。"""

from __future__ import annotations

import copy
from typing import Any, Callable

from .events import TAG_KEY
from .transport import Transport
from .view import View


class ViewSession:
    """管理一个 View 实例的生命周期。

    职责：
    1. 调用 view.render() 获取组件树
    2. 处理树中的 callable/bind（提取到 callback registry，替换为 $ 标签）
    3. 通过 transport 发送序列化后的 JSON
    4. 接收前端事件，dispatch 到对应的 callback
    5. 事件处理后自动 re-render + 推送
    """

    def __init__(self, view: View, transport: Transport) -> None:
        self.view = view
        self.transport = transport
        self._callbacks: dict[tuple[str, str], Callable[..., Any]] = {}

    async def initialize(self) -> None:
        """首次 render，推送完整树。"""
        await self._render_and_send()

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 → dispatch → re-render → 推送。"""
        source = event.get("source", "")
        event_name = event.get("event", "")
        data = event.get("data", {})

        key = (source, event_name)
        cb = self._callbacks.get(key)
        if cb is not None:
            cb(data)
        else:
            self.view.on_event(event)

        await self._render_and_send()

    async def push(self) -> None:
        """主动推送当前 view 状态。

        应用层可调用此方法通知其他连接刷新（如共享 view 广播场景）。
        """
        await self._render_and_send()

    async def _render_and_send(self) -> None:
        """render → process → send。"""
        raw_tree = self.view.render()
        # 归一化：dict → list
        if isinstance(raw_tree, dict):
            tree = [raw_tree]
        else:
            tree = list(raw_tree)

        self._callbacks.clear()
        wire_tree = [self._process_node(node) for node in tree]
        await self.transport.send({"type": "render", "tree": wire_tree})

    def _process_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """处理单个组件节点：提取 callable，处理 children。"""
        result: dict[str, Any] = {}
        node_id = node.get("id", "")

        for key, val in node.items():
            if key == "children" and isinstance(val, list):
                # 递归处理子组件
                result[key] = [self._process_node(child) for child in val]
            elif isinstance(val, dict) and TAG_KEY in val:
                result[key] = self._process_tagged(val, node_id, key)
            else:
                result[key] = val

        return result

    def _process_tagged(
        self, tagged: dict[str, Any], node_id: str, prop_name: str
    ) -> dict[str, Any]:
        """处理 $ 标签值：提取 callable，生成 wire 格式。"""
        tag_type = tagged[TAG_KEY]

        if tag_type == "handler":
            fn = tagged.get("fn")
            extract = tagged.get("extract", {})
            if fn is not None:
                # handler(fn, **extract) — 注册 callback
                self._callbacks[(node_id, prop_name)] = fn
            # else: notify(**extract) — fallback 到 view.on_event()
            return {TAG_KEY: "handler", "extract": extract}

        elif tag_type == "bind":
            obj = tagged["obj"]
            attr = tagged["attr"]
            path = tagged.get("path", "$0")
            # 生成写回 callback
            self._callbacks[(node_id, prop_name)] = _make_bind_callback(
                obj, attr
            )
            return {TAG_KEY: "handler", "extract": {"__bind_value__": path}}

        else:
            # 未知标签类型，原样传递
            return copy.deepcopy(tagged)


def _make_bind_callback(obj: Any, attr: str) -> Callable[..., Any]:
    """创建 bind 的写回 callback。"""
    def callback(data: dict[str, Any]) -> None:
        value = data.get("__bind_value__")
        setattr(obj, attr, value)
    return callback
