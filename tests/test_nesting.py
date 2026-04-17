"""View 嵌套的单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewPort, Channel, handler, bind
from mutgui._view_impl import ViewObservers


class MockChannel(Channel):
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def messages_for(self, view_id: list[str | int]) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("viewId") == view_id]


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 测试用 View
# ---------------------------------------------------------------------------

class ChildView(View):
    id = "child"

    def __init__(self) -> None:
        self.value = 0

    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "InputNumber", "$id": "val", "value": self.value,
             "onChange": handler(self.on_change, value="$0")},
        ]

    def on_change(self, data: dict[str, Any]) -> None:
        self.value = data["value"]


class ParentView(View):
    def __init__(self) -> None:
        self.child = ChildView()
        self.title = "Parent"

    def render(self) -> list[Any]:
        return [
            {"$component": "Text", "$id": "title", "children": self.title},
            self.child,
        ]


# ---------------------------------------------------------------------------
# 嵌套 render
# ---------------------------------------------------------------------------

def test_nested_render_produces_view_and_child_messages() -> None:
    """嵌套 View render 产出父 + 子两条消息，父先子后。"""
    channel = MockChannel()
    view = ParentView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    assert len(channel.messages) == 2

    # 父 View：viewId=[], tree 包含 $view 引用
    parent_msg = channel.messages[0]
    assert parent_msg["viewId"] == []
    assert parent_msg["tree"][0]["$component"] == "Text"
    assert parent_msg["tree"][1] == {"$view": "child"}

    # 子 View：viewId=["child"]
    child_msg = channel.messages[1]
    assert child_msg["viewId"] == ["child"]
    assert child_msg["tree"][0]["$component"] == "InputNumber"
    assert child_msg["tree"][0]["value"] == 0


# ---------------------------------------------------------------------------
# 事件路由
# ---------------------------------------------------------------------------

def test_event_routes_to_child_view() -> None:
    """事件 source 数组正确路由到子 View handler。"""
    channel = MockChannel()
    view = ParentView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    run(vp.handle_event({
        "source": ["child", "val"],
        "event": "onChange",
        "data": {"value": 42},
    }))

    assert view.child.value == 42

    # flush 后子 View 重新 render
    child_msgs = channel.messages_for(["child"])
    assert len(child_msgs) == 2  # initial + after event
    assert child_msgs[-1]["tree"][0]["value"] == 42


def test_event_to_parent_component() -> None:
    """事件路由到父 View 的组件。"""
    channel = MockChannel()

    class ParentWithHandler(View):
        def __init__(self) -> None:
            self.clicked = False
            self.child = ChildView()

        def render(self) -> list[Any]:
            return [
                {"$component": "Button", "$id": "btn",
                 "onClick": handler(self.on_click)},
                self.child,
            ]

        def on_click(self, data: dict[str, Any]) -> None:
            self.clicked = True

    view = ParentWithHandler()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    run(vp.handle_event({
        "source": ["btn"],
        "event": "onClick",
        "data": {},
    }))

    assert view.clicked is True


# ---------------------------------------------------------------------------
# 深层嵌套
# ---------------------------------------------------------------------------

def test_deeply_nested_event_routing() -> None:
    """三层嵌套事件路由。"""
    channel = MockChannel()

    class InnerView(View):
        id = "inner"

        def __init__(self) -> None:
            self.val = ""

        def render(self) -> list[dict[str, Any]]:
            return [{"$component": "Input", "$id": "txt", "value": self.val,
                     "onChange": handler(self.on_change, value="$0")}]

        def on_change(self, data: dict[str, Any]) -> None:
            self.val = data["value"]

    class MiddleView(View):
        id = "middle"

        def __init__(self) -> None:
            self.inner = InnerView()

        def render(self) -> list[Any]:
            return [self.inner]

    class RootView(View):
        def __init__(self) -> None:
            self.middle = MiddleView()

        def render(self) -> list[Any]:
            return [self.middle]

    view = RootView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    # 3 层 → 3 条消息
    assert len(channel.messages) == 3
    assert channel.messages[0]["viewId"] == []
    assert channel.messages[1]["viewId"] == ["middle"]
    assert channel.messages[2]["viewId"] == ["middle", "inner"]

    # 事件路由到最内层
    run(vp.handle_event({
        "source": ["middle", "inner", "txt"],
        "event": "onChange",
        "data": {"value": "hello"},
    }))

    assert view.middle.inner.val == "hello"


# ---------------------------------------------------------------------------
# invalidate 合并
# ---------------------------------------------------------------------------

def test_invalidate_coalescing() -> None:
    """连续多次 invalidate → 只产生一次 render 推送。"""
    channel = MockChannel()
    view = ChildView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    initial_count = len(channel.messages)

    view.invalidate()
    view.invalidate()
    view.invalidate()

    run(vp.flush())
    assert len(channel.messages) == initial_count + 1


def test_child_invalidate_no_parent_render() -> None:
    """子 View invalidate 不触发父 View render。"""
    channel = MockChannel()
    view = ParentView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    initial_count = len(channel.messages)  # 2 (parent + child)

    view.child.invalidate()
    run(vp.flush())

    # 只有子 View 重新 render（1 条新消息）
    assert len(channel.messages) == initial_count + 1
    last_msg = channel.messages[-1]
    assert last_msg["viewId"] == ["child"]


# ---------------------------------------------------------------------------
# View 在 $children 中
# ---------------------------------------------------------------------------

def test_view_inside_children() -> None:
    """View 实例出现在组件的 $children 中。"""
    channel = MockChannel()

    class PanelView(View):
        id = "panel"

        def render(self) -> list[dict[str, Any]]:
            return [{"$component": "Text", "$id": "label", "children": "Panel"}]

    class TabsView(View):
        def __init__(self) -> None:
            self.panel = PanelView()

        def render(self) -> list[Any]:
            return [
                {"$component": "Tabs", "$id": "tabs", "$children": [
                    {"$component": "Tabs.TabPane", "$id": "tab1", "tab": "Tab 1",
                     "$children": [self.panel]},
                ]},
            ]

    view = TabsView()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    # 父 View 的 tree 中 $children 包含 $view 引用
    parent_tree = channel.messages[0]["tree"]
    tab_pane = parent_tree[0]["$children"][0]
    assert tab_pane["$children"] == [{"$view": "panel"}]

    # 子 View 独立推送
    assert channel.messages[1]["viewId"] == ["panel"]
    assert channel.messages[1]["tree"][0]["$component"] == "Text"


# ---------------------------------------------------------------------------
# 动态增删 View
# ---------------------------------------------------------------------------

def test_dynamic_view_add_remove() -> None:
    """父 View re-render 时子 View 出现/消失。"""
    channel = MockChannel()

    class DynamicParent(View):
        def __init__(self) -> None:
            self.child = ChildView()
            self.show_child = True

        def render(self) -> list[Any]:
            items: list[Any] = [
                {"$component": "Text", "$id": "title", "children": "Dynamic"},
            ]
            if self.show_child:
                items.append(self.child)
            return items

    view = DynamicParent()
    vp = ViewPort(view, channel)
    run(vp.initialize())

    # 初始：parent + child = 2 消息
    assert len(channel.messages) == 2

    # 隐藏 child → re-render parent
    view.show_child = False
    view.invalidate()
    run(vp.flush())

    # parent re-rendered, child 不在 tree 中
    parent_msgs = [m for m in channel.messages if m["viewId"] == []]
    last_parent = parent_msgs[-1]
    assert len(last_parent["tree"]) == 1  # 只有 Text

    # child 的 ViewPort 已 detach（ViewObservers 中不再有该 ViewPort）
    obs = ViewObservers.get(view.child)
    if obs is not None:
        assert len(obs._viewports) == 0


# ---------------------------------------------------------------------------
# 多客户端共享 View
# ---------------------------------------------------------------------------

def test_multi_client_invalidate_notifies_all() -> None:
    """同一 View 被多个 ViewPort 观察，invalidate 通知所有。"""
    ch_a = MockChannel()
    ch_b = MockChannel()
    view = ChildView()

    vp_a = ViewPort(view, ch_a)
    vp_b = ViewPort(view, ch_b)
    run(vp_a.initialize())
    run(vp_b.initialize())

    assert len(ch_a.messages) == 1
    assert len(ch_b.messages) == 1

    # 通过 vp_a 修改状态
    run(vp_a.handle_event({
        "source": ["val"], "event": "onChange",
        "data": {"value": 99},
    }))
    assert view.value == 99

    # vp_a 已经 flush（handle_event 自动 flush）
    assert len(ch_a.messages) == 2

    # vp_b 被 invalidate 标脏，手动 flush
    run(vp_b.flush())
    assert len(ch_b.messages) == 2
    assert ch_b.messages[-1]["tree"][0]["value"] == 99


def test_detach_removes_observer() -> None:
    """detach 后 invalidate 不再通知该 ViewPort。"""
    ch_a = MockChannel()
    ch_b = MockChannel()
    view = ChildView()

    vp_a = ViewPort(view, ch_a)
    vp_b = ViewPort(view, ch_b)
    run(vp_a.initialize())
    run(vp_b.initialize())

    vp_a.detach()

    obs = ViewObservers.get(view)
    assert obs is not None
    assert len(obs._viewports) == 1
    assert obs._viewports[0] is vp_b
