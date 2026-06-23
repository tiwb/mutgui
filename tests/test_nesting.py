"""View 嵌套的单元测试。"""

import asyncio
from typing import Any

import mutobj

from mutgui import View, ViewBlock, ViewPort, Channel, Callback, Expr
from mutgui._view_impl import ViewObservers


class MockChannel(Channel):
    messages: list[dict[str, Any]] = mutobj.field(default_factory=list)

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def messages_for(self, view_id: list[str | int]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for m in self.messages:
            if m.get("type") == "render":
                for f in m.get("frames", []):
                    if f.get("viewId") == view_id:
                        result.append(f)
        return result


# ---------------------------------------------------------------------------
# 测试用 View
# ---------------------------------------------------------------------------

class ChildView(View):
    id = "child"
    value: Any = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "InputNumber", "$id": "val", "value": self.value,
             "onChange": Callback(self.on_change, Expr.wire("$0"))},
        ])

    def on_change(self, value: Any) -> None:
        self.value = value
        self.invalidate()


class ParentView(View):
    child: View
    title: str

    def __init__(self) -> None:
        super().__init__()
        self.child = ChildView()
        self.title = "Parent"

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Text", "$id": "title", "children": self.title},
            self.child,
        ])


# ---------------------------------------------------------------------------
# 嵌套 render
# ---------------------------------------------------------------------------

def test_nested_render_produces_view_and_child_messages() -> None:
    """嵌套 View render 产出父 + 子两条消息，父先子后。"""
    async def _test() -> None:
        channel = MockChannel()
        view = ParentView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        assert len(channel.messages) == 1
        frames = channel.messages[0]["frames"]
        assert len(frames) == 2

        # 父 View：viewId=[], tree 包含 $view 引用
        parent_msg = frames[0]
        assert parent_msg["viewId"] == []
        assert parent_msg["tree"][0]["$component"] == "Text"
        assert parent_msg["tree"][1] == {"$view": "child"}

        # 子 View：viewId=["child"]
        child_msg = frames[1]
        assert child_msg["viewId"] == ["child"]
        assert child_msg["tree"][0]["$component"] == "InputNumber"
        assert child_msg["tree"][0]["value"] == 0

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 事件路由
# ---------------------------------------------------------------------------

def test_event_routes_to_child_view() -> None:
    """事件 source 数组正确路由到子 View handler。"""
    async def _test() -> None:
        channel = MockChannel()
        view = ParentView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["child", "val"],
            "event": "onChange",
            "handlerId": 0,
            "data": {"$args": [42]},
        })
        await view.child.rendered()

        assert view.child.value == 42

        # 子 View 重新 render
        child_msgs = channel.messages_for(["child"])
        assert len(child_msgs) == 2  # initial + after event
        assert child_msgs[-1]["tree"][0]["value"] == 42

    asyncio.run(_test())


def test_event_to_parent_component() -> None:
    """事件路由到父 View 的组件。"""
    async def _test() -> None:
        channel = MockChannel()

        class ParentWithHandler(View):
            clicked: bool
            child: View

            def __init__(self) -> None:
                super().__init__()
                self.clicked = False
                self.child = ChildView()

            def render(self) -> ViewBlock:
                return ViewBlock([
                    {"$component": "Button", "$id": "btn",
                     "onClick": Callback(self.on_click)},
                    self.child,
                ])

            def on_click(self) -> None:
                self.clicked = True

        view = ParentWithHandler()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["btn"],
            "event": "onClick",
            "handlerId": 0,
            "data": {},
        })
        await view.rendered()

        assert view.clicked is True

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 深层嵌套
# ---------------------------------------------------------------------------

def test_deeply_nested_event_routing() -> None:
    """三层嵌套事件路由。"""
    async def _test() -> None:
        channel = MockChannel()

        class InnerView(View):
            id = "inner"
            val: str

            def __init__(self) -> None:
                super().__init__()
                self.val = ""

            def render(self) -> ViewBlock:
                return ViewBlock([{"$component": "Input", "$id": "txt", "value": self.val,
                         "onChange": Callback(self.on_change, Expr.wire("$0"))}])

            def on_change(self, value: Any) -> None:
                self.val = value

        class MiddleView(View):
            id = "middle"
            inner: View

            def __init__(self) -> None:
                super().__init__()
                self.inner = InnerView()

            def render(self) -> ViewBlock:
                return ViewBlock([self.inner])

        class RootView(View):
            middle: View

            def __init__(self) -> None:
                super().__init__()
                self.middle = MiddleView()

            def render(self) -> ViewBlock:
                return ViewBlock([self.middle])

        view = RootView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        # 3 层 → 1 条 render 消息，3 帧
        assert len(channel.messages) == 1
        frames = channel.messages[0]["frames"]
        assert len(frames) == 3
        assert frames[0]["viewId"] == []
        assert frames[1]["viewId"] == ["middle"]
        assert frames[2]["viewId"] == ["middle", "inner"]

        # 事件路由到最内层
        await vp.handle_event({
            "source": ["middle", "inner", "txt"],
            "event": "onChange",
            "handlerId": 0,
            "data": {"$args": ["hello"]},
        })
        await view.middle.inner.rendered()

        assert view.middle.inner.val == "hello"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# invalidate 合并
# ---------------------------------------------------------------------------

def test_invalidate_coalescing() -> None:
    """连续多次 invalidate → 只产生一次 render 推送。"""
    async def _test() -> None:
        channel = MockChannel()
        view = ChildView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        initial_count = len(channel.messages)

        view.invalidate()
        view.invalidate()
        view.invalidate()

        await view.rendered()
        assert len(channel.messages) == initial_count + 1

    asyncio.run(_test())


def test_child_invalidate_no_parent_render() -> None:
    """子 View invalidate 不触发父 View render。"""
    async def _test() -> None:
        channel = MockChannel()
        view = ParentView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        initial_count = len(channel.messages)  # 1

        view.child.invalidate()
        await view.child.rendered()

        # 只有子 View 重新 render（1 条新消息，含 1 帧）
        assert len(channel.messages) == initial_count + 1
        last_msg = channel.messages[-1]
        frames = last_msg["frames"]
        assert len(frames) == 1
        assert frames[0]["viewId"] == ["child"]

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# View 在 $children 中
# ---------------------------------------------------------------------------

def test_view_inside_children() -> None:
    """View 实例出现在组件的 $children 中。"""
    async def _test() -> None:
        channel = MockChannel()

        class PanelView(View):
            id = "panel"

            def render(self) -> ViewBlock:
                return ViewBlock([{"$component": "Text", "$id": "label", "children": "Panel"}])

        class TabsView(View):
            panel: View

            def __init__(self) -> None:
                super().__init__()
                self.panel = PanelView()

            def render(self) -> ViewBlock:
                return ViewBlock([
                    {"$component": "Tabs", "$id": "tabs", "$children": [
                        {"$component": "Tabs.TabPane", "$id": "tab1", "tab": "Tab 1",
                         "$children": [self.panel]},
                    ]},
                ])

        view = TabsView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        # 父 View 的 tree 中 $children 包含 $view 引用
        frames = channel.messages[0]["frames"]
        parent_tree = frames[0]["tree"]
        tab_pane = parent_tree[0]["$children"][0]
        assert tab_pane["$children"] == [{"$view": "panel"}]

        # 子 View 独立推送（同一 render 消息的不同帧）
        assert frames[1]["viewId"] == ["panel"]
        assert frames[1]["tree"][0]["$component"] == "Text"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 动态增删 View
# ---------------------------------------------------------------------------

def test_dynamic_view_add_remove() -> None:
    """父 View re-render 时子 View 出现/消失。"""
    async def _test() -> None:
        channel = MockChannel()

        class DynamicParent(View):
            child: View
            show_child: bool

            def __init__(self) -> None:
                super().__init__()
                self.child = ChildView()
                self.show_child = True

            def render(self) -> ViewBlock:
                items: list[Any] = [
                    {"$component": "Text", "$id": "title", "children": "Dynamic"},
                ]
                if self.show_child:
                    items.append(self.child)
                return ViewBlock(items)

        view = DynamicParent()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        # 初始：parent + child = 1 条 render 消息，2 帧
        assert len(channel.messages) == 1
        assert len(channel.messages[0]["frames"]) == 2

        # 隐藏 child → re-render parent
        view.show_child = False
        view.invalidate()
        await view.rendered()

        # parent re-rendered, child 不在 tree 中
        parent_frames = [f for m in channel.messages if m.get("type") == "render"
                         for f in m.get("frames", []) if f["viewId"] == []]
        last_parent = parent_frames[-1]
        assert len(last_parent["tree"]) == 1  # 只有 Text

        # child 的 ViewPort 已 detach（ViewObservers 中不再有该 ViewPort）
        obs = ViewObservers.get(view.child)
        if obs is not None:
            assert len(obs.viewports) == 0

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 多客户端共享 View
# ---------------------------------------------------------------------------

def test_multi_client_invalidate_notifies_all() -> None:
    """同一 View 被多个 ViewPort 观察，invalidate 自动 push 给所有。"""
    async def _test() -> None:
        ch_a = MockChannel()
        ch_b = MockChannel()
        view = ChildView()

        vp_a = ViewPort(view, ch_a)
        await vp_a.initialize()
        await view.rendered()
        assert len(ch_a.messages) == 1

        vp_b = ViewPort(view, ch_b)
        await vp_b.initialize()
        # vp_b.initialize() 检测到 View 已 clean，直接推送缓存
        assert len(ch_b.messages) == 1

        # 通过 vp_a 修改状态 → 自动 push 给所有 ViewPort
        await vp_a.handle_event({
            "source": ["val"], "event": "onChange",
            "handlerId": 0,
            "data": {"$args": [99]},
        })
        await view.rendered()
        assert view.value == 99

        # 两个 channel 都收到更新，无需手动 flush
        assert len(ch_a.messages) == 2
        assert len(ch_b.messages) == 2
        ch_b_frames = ch_b.messages[-1]["frames"]
        assert any(f["tree"][0]["value"] == 99 for f in ch_b_frames)

    asyncio.run(_test())


def test_detach_removes_observer() -> None:
    """detach 后 invalidate 不再通知该 ViewPort。"""
    async def _test() -> None:
        ch_a = MockChannel()
        ch_b = MockChannel()
        view = ChildView()

        vp_a = ViewPort(view, ch_a)
        vp_b = ViewPort(view, ch_b)
        await vp_a.initialize()
        await view.rendered()
        await vp_b.initialize()

        vp_a.detach()

        obs = ViewObservers.get(view)
        assert obs is not None
        assert len(obs.viewports) == 1
        assert obs.viewports[0] is vp_b

    asyncio.run(_test())
