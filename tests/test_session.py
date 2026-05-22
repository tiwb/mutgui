"""ViewPort 的单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewBlock, ViewPort, Channel, Callback, Bind, EventHandler, Expr
from mutgui.events import Event


class MockChannel(Channel):
    """记录所有发送消息的 mock channel。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def last(self) -> dict[str, Any]:
        return self.messages[-1]

    @property
    def last_tree(self) -> list[dict[str, Any]]:
        return self.last["tree"]


# ---------------------------------------------------------------------------
# 基础 render
# ---------------------------------------------------------------------------

class SimpleView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Input", "$id": "name", "value": "hello"},
        ])


def test_initialize_sends_render() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = SimpleView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        assert len(channel.messages) == 1
        msg = channel.last
        assert msg["type"] == "render"
        assert msg["viewId"] == []
        assert len(msg["tree"]) == 1
        assert msg["tree"][0]["$component"] == "Input"
        assert msg["tree"][0]["value"] == "hello"

    asyncio.run(_test())


def test_plain_props_pass_through() -> None:
    """没有 $handler 标签的 props 应原样传递。"""

    class StyledView(View):
        def render(self) -> ViewBlock:
            return ViewBlock([{"$component": "Input", "$id": "x", "style": {"width": 200}, "placeholder": "hi"}])

    async def _test() -> None:
        channel = MockChannel()
        view = StyledView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        node = channel.last_tree[0]
        assert node["style"] == {"width": 200}
        assert node["placeholder"] == "hi"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class CallbackView(View):
    def __init__(self) -> None:
        super().__init__()
        self.clicked = False

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Button", "$id": "btn", "onClick": Callback(self.on_click)},
        ])

    def on_click(self) -> None:
        self.clicked = True


def test_callback_registered_and_dispatched() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = CallbackView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        # wire 格式应该有 $handler
        node = channel.last_tree[0]
        assert "$handler" in node["onClick"]
        assert node["onClick"] == {"$handler": 0}

        # dispatch event
        await vp.handle_event({"source": ["btn"], "event": "onClick", "handlerId": 0, "data": {}})
        await view.rendered()
        assert view.clicked is True

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------

class BindView(View):
    def __init__(self) -> None:
        super().__init__()
        self.name = ""
        self.age = 18

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Input", "$id": "name", "value": self.name,
             "onChange": Bind(self, "name", "$0.target.value")},
            {"$component": "InputNumber", "$id": "age", "value": self.age,
             "onChange": Bind(self, "age", "$0")},
        ])


def test_bind_wire_format() -> None:
    """Bind 应序列化为 $handler + $args 格式。"""
    async def _test() -> None:
        channel = MockChannel()
        view = BindView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        node = channel.last_tree[0]
        on_change = node["onChange"]
        assert "$handler" in on_change
        assert on_change["args"] == ["$0.target.value"]
        assert "obj" not in on_change
        assert "attr" not in on_change

    asyncio.run(_test())


def test_bind_setattr() -> None:
    """bind event 应写回对象属性。"""
    async def _test() -> None:
        channel = MockChannel()
        view = BindView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["name"], "event": "onChange",
            "handlerId": 0,
            "data": {"$args": ["Alice"]},
        })
        await view.rendered()
        assert view.name == "Alice"

        # 验证 re-render 中值已更新
        name_node = next(n for n in channel.last_tree if n.get("$id") == "name")
        assert name_node["value"] == "Alice"

    asyncio.run(_test())


def test_bind_number() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = BindView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["age"], "event": "onChange",
            "handlerId": 1,
            "data": {"$args": [25]},
        })
        await view.rendered()
        assert view.age == 25

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# EventHandler (只提取，不消费，落到 on_event)
# ---------------------------------------------------------------------------

class EventHandlerView(View):
    def __init__(self) -> None:
        super().__init__()
        self.last_event: Event | None = None

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Input", "$id": "x",
             "onChange": EventHandler(value=Expr.wire("$0.target.value"))},
        ])

    async def on_event(self, event: Event) -> bool:
        handled = await super().on_event(event)
        if not handled:
            self.last_event = event
            return True
        return handled


def test_event_handler_falls_through_to_on_event() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = EventHandlerView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["x"], "event": "onChange",
            "data": {"value": "test"},
        })
        assert view.last_event is not None
        assert view.last_event.component_id == "x"
        assert view.last_event.name == "onChange"
        assert view.last_event.kwargs == {"value": "test"}

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 条件渲染
# ---------------------------------------------------------------------------

class ConditionalView(View):
    def __init__(self) -> None:
        super().__init__()
        self.show_extra = False

    def render(self) -> ViewBlock:
        tree: list[dict[str, Any]] = [
            {"$component": "Checkbox", "$id": "toggle", "checked": self.show_extra,
             "onChange": Bind(self, "show_extra", "$0.target.checked")},
        ]
        if self.show_extra:
            tree.append({"$component": "Input", "$id": "extra", "value": ""})
        return ViewBlock(tree)


def test_conditional_rendering() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = ConditionalView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        assert len(channel.last_tree) == 1

        await vp.handle_event({
            "source": ["toggle"], "event": "onChange",
            "handlerId": 0,
            "data": {"$args": [True]},
        })
        await view.rendered()
        assert len(channel.last_tree) == 2
        assert channel.last_tree[1]["$id"] == "extra"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 单根组件（dict）
# ---------------------------------------------------------------------------

class SingleRootView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([{"$component": "Button", "$id": "ok", "children": "OK"}])


def test_single_root_dict() -> None:
    """render() 返回包含单个组件的 ViewBlock。"""
    async def _test() -> None:
        channel = MockChannel()
        view = SingleRootView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        assert len(channel.last_tree) == 1
        assert channel.last_tree[0]["children"] == "OK"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 嵌套 $children
# ---------------------------------------------------------------------------

class NestedChildrenView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Card", "$id": "card", "$children": [
                {"$component": "Input", "$id": "inner", "value": "nested",
                 "onChange": Bind(self, "_dummy", "$0")},
            ]},
        ])

    _dummy: str = ""


def test_nested_children() -> None:
    """$children 列表应被递归处理。"""
    async def _test() -> None:
        channel = MockChannel()
        view = NestedChildrenView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        card = channel.last_tree[0]
        assert card["$component"] == "Card"
        assert isinstance(card["$children"], list)
        inner = card["$children"][0]
        assert inner["$component"] == "Input"
        assert inner["value"] == "nested"
        assert "$handler" in inner["onChange"]
        assert inner["onChange"]["args"] == ["$0"]

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Callback 不自动 invalidate
# ---------------------------------------------------------------------------

def test_callback_does_not_auto_invalidate() -> None:
    """Callback 事件不应自动 invalidate（与旧行为不同）。"""

    class CountView(View):
        def __init__(self) -> None:
            super().__init__()
            self.count = 0

        def render(self) -> ViewBlock:
            return ViewBlock([
                {"$component": "Button", "$id": "btn",
                 "onClick": Callback(self.on_click), "label": str(self.count)},
            ])

        def on_click(self) -> None:
            self.count += 1

    async def _test() -> None:
        channel = MockChannel()
        view = CountView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        initial_count = len(channel.messages)

        await vp.handle_event({"source": ["btn"], "event": "onClick", "handlerId": 0, "data": {}})
        # Callback 不自动 invalidate，不应产生新 render
        await asyncio.sleep(0.05)
        assert len(channel.messages) == initial_count
        assert view.count == 1

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Bind 自动 invalidate
# ---------------------------------------------------------------------------

def test_bind_auto_invalidates() -> None:
    """Bind 事件应自动 invalidate 并 re-render。"""
    async def _test() -> None:
        channel = MockChannel()
        view = BindView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        initial_count = len(channel.messages)

        await vp.handle_event({
            "source": ["name"], "event": "onChange",
            "handlerId": 0,
            "data": {"$args": ["Bob"]},
        })
        await view.rendered()

        assert len(channel.messages) > initial_count
        assert view.name == "Bob"

    asyncio.run(_test())
