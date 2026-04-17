"""ViewSession — 管理 View 的 render→serialize→send 循环（支持嵌套）。"""

from __future__ import annotations

import copy
from typing import Any, Callable

from .events import TAG_KEY
from .transport import Transport
from .view import View


class ViewSession:
    """管理一个 View 实例及其嵌套子 View 的生命周期。

    职责：
    1. 调用 view.render() 获取组件树（可包含子 View 实例）
    2. 处理树中的 callable/bind（提取到 callback registry，替换为 $ 标签）
    3. 识别子 View 实例，创建子 ViewSession（递归）
    4. 通过 transport 发送序列化后的 JSON（含 viewId 路径）
    5. 接收前端事件，按 source 数组逐层路由到对应的 ViewSession
    6. 事件处理后自动 flush dirty views
    """

    def __init__(
        self,
        view: View,
        transport: Transport,
        *,
        _path: list[str | int] | None = None,
    ) -> None:
        self.view = view
        self.transport = transport
        self._path: list[str | int] = _path if _path is not None else []
        self._callbacks: dict[tuple[str | int, str], Callable[..., Any]] = {}
        self._children: dict[str | int, ViewSession] = {}
        self._dirty = True  # 首次需要 render
        view._session = self

    async def initialize(self) -> None:
        """首次 render，推送完整树。先推父，再推子。"""
        await self._flush_tree()

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 → 路由 → flush dirty views。"""
        source = event.get("source", [])
        event_name = event.get("event", "")
        data = event.get("data", {})

        # 防御：字符串 source 转为数组
        if isinstance(source, str):
            source = [source] if source else []

        self._route_event(source, event_name, data, event)
        await self._flush_tree()

    async def flush(self) -> None:
        """Flush 所有 dirty views。

        配合 invalidate() 使用：invalidate 标脏，flush 推送。
        """
        await self._flush_tree()

    async def push(self) -> None:
        """强制推送整棵 view 树（无论是否 dirty）。

        用于共享 view 广播场景：状态被其他 session 修改后，
        通过 push() 通知本 session 的客户端。
        """
        await self._render_and_send()
        self._dirty = False
        for child in list(self._children.values()):
            await child.push()

    def _mark_dirty(self) -> None:
        """标记当前 View 需要 re-render。"""
        self._dirty = True

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _route_event(
        self,
        source: list[str | int],
        event_name: str,
        data: dict[str, Any],
        original_event: dict[str, Any],
    ) -> None:
        """按 source 数组逐层路由事件。"""
        if len(source) > 1:
            # 首段是子 View id，向下路由
            child_id = source[0]
            child = self._children.get(child_id)
            if child is not None:
                child._route_event(source[1:], event_name, data, original_event)
        elif len(source) == 1:
            # 末段是组件 $id，本地处理
            component_id = source[0]
            key = (component_id, event_name)
            cb = self._callbacks.get(key)
            if cb is not None:
                cb(data)
            else:
                self.view.on_event(original_event)
            self._mark_dirty()
        else:
            self.view.on_event(original_event)
            self._mark_dirty()

    async def _flush_tree(self) -> None:
        """Flush self（if dirty）then children。父先子后。"""
        if self._dirty:
            await self._render_and_send()
            self._dirty = False
        for child in list(self._children.values()):
            await child._flush_tree()

    async def _render_and_send(self) -> None:
        """render → process → send。"""
        raw_tree = self.view.render()
        # 归一化：dict → list
        if isinstance(raw_tree, dict):
            items: list[Any] = [raw_tree]
        else:
            items = list(raw_tree)

        self._callbacks.clear()
        old_children = self._children
        self._children = {}

        wire_tree = self._process_items(items, old_children)

        # 清理被移除的子 View 的 session 引用
        for child_session in old_children.values():
            if child_session.view._session is child_session:
                child_session.view._session = None

        await self.transport.send({
            "type": "render",
            "viewId": self._path,
            "tree": wire_tree,
        })

    def _process_items(
        self,
        items: list[Any],
        old_children: dict[str | int, ViewSession],
    ) -> list[dict[str, Any]]:
        """处理列表：组件 dict 或 View 实例。"""
        result: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, View):
                vid = item.id
                # 复用已有子 session（同一 View 实例）或新建
                if vid in old_children and old_children[vid].view is item:
                    child = old_children.pop(vid)
                else:
                    child_path = self._path + [vid]
                    child = ViewSession(
                        item, self.transport, _path=child_path,
                    )
                self._children[vid] = child
                result.append({"$view": vid})
            else:
                result.append(self._process_node(item, old_children))
        return result

    def _process_node(
        self,
        node: dict[str, Any],
        old_children: dict[str | int, ViewSession],
    ) -> dict[str, Any]:
        """处理单个组件节点：提取 callable，处理 $children。"""
        result: dict[str, Any] = {}
        node_id: str | int = node.get("$id", "")

        for key, val in node.items():
            if key == "$children" and isinstance(val, list):
                # $children 递归处理（可包含 View 实例）
                result[key] = self._process_items(val, old_children)
            elif isinstance(val, dict) and TAG_KEY in val:
                result[key] = self._process_tagged(val, node_id, key)
            else:
                result[key] = val

        return result

    def _process_tagged(
        self, tagged: dict[str, Any], node_id: str | int, prop_name: str,
    ) -> dict[str, Any]:
        """处理 $ 标签值：提取 callable，生成 wire 格式。"""
        tag_type = tagged[TAG_KEY]

        if tag_type == "handler":
            fn = tagged.get("fn")
            extract = tagged.get("extract", {})
            if fn is not None:
                self._callbacks[(node_id, prop_name)] = fn
            return {TAG_KEY: "handler", "extract": extract}

        elif tag_type == "bind":
            obj = tagged["obj"]
            attr = tagged["attr"]
            path = tagged.get("path", "$0")
            self._callbacks[(node_id, prop_name)] = _make_bind_callback(
                obj, attr,
            )
            return {TAG_KEY: "handler", "extract": {"__bind_value__": path}}

        else:
            return copy.deepcopy(tagged)


def _make_bind_callback(obj: Any, attr: str) -> Callable[..., Any]:
    """创建 bind 的写回 callback。"""
    def callback(data: dict[str, Any]) -> None:
        value = data.get("__bind_value__")
        setattr(obj, attr, value)
    return callback
