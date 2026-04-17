"""ViewPort 的单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewPort, Channel, bind, handler, notify
from mutgui.events import TAG_KEY


class MockChannel(Channel):
    """记录所有发送消息的 mock channel。"""

    def __init__(self) -> None:
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
    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Input", "$id": "name", "value": "hello"},
        ]


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
    """没有 $ 标签的 props 应原样传递。"""

    class StyledView(View):
        def render(self) -> list[dict[str, Any]]:
            return [{"$component": "Input", "$id": "x", "style": {"width": 200}, "placeholder": "hi"}]

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
# handler
# ---------------------------------------------------------------------------

class HandlerView(View):
    def __init__(self) -> None:
        self.clicked = False

    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Button", "$id": "btn", "onClick": handler(self.on_click)},
        ]

    def on_click(self, data: dict[str, Any]) -> None:
        self.clicked = True


def test_handler_registered_and_dispatched() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = HandlerView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        # wire 格式应该有 $ tag 但无 fn
        node = channel.last_tree[0]
        assert node["onClick"][TAG_KEY] == "handler"
        assert "fn" not in node["onClick"]

        # dispatch event（source 数组格式）
        await vp.handle_event({"source": ["btn"], "event": "onClick", "data": {}})
        await view.rendered()
        assert view.clicked is True
        # re-render 后应多一条消息
        assert len(channel.messages) == 2

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# bind
# ---------------------------------------------------------------------------

class BindView(View):
    def __init__(self) -> None:
        self.name = ""
        self.age = 18

    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Input", "$id": "name", "value": self.name,
             "onChange": bind(self, "name", "$0.target.value")},
            {"$component": "InputNumber", "$id": "age", "value": self.age,
             "onChange": bind(self, "age", "$0")},
        ]


def test_bind_wire_format() -> None:
    """bind 应序列化为 handler + __bind_value__ 提取。"""
    async def _test() -> None:
        channel = MockChannel()
        view = BindView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        node = channel.last_tree[0]
        on_change = node["onChange"]
        assert on_change[TAG_KEY] == "handler"
        assert on_change["extract"]["__bind_value__"] == "$0.target.value"
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
            "data": {"__bind_value__": "Alice"},
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
            "data": {"__bind_value__": 25},
        })
        await view.rendered()
        assert view.age == 25

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# notify (fallback to on_event)
# ---------------------------------------------------------------------------

class NotifyView(View):
    def __init__(self) -> None:
        self.last_event: dict[str, Any] | None = None

    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Input", "$id": "x",
             "onChange": notify(value="$0.target.value")},
        ]

    def on_event(self, event: dict[str, Any]) -> None:
        self.last_event = event


def test_notify_falls_back_to_on_event() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = NotifyView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        await vp.handle_event({
            "source": ["x"], "event": "onChange",
            "data": {"value": "test"},
        })
        await view.rendered()
        assert view.last_event is not None
        assert view.last_event["source"] == ["x"]

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 条件渲染
# ---------------------------------------------------------------------------

class ConditionalView(View):
    def __init__(self) -> None:
        self.show_extra = False

    def render(self) -> list[dict[str, Any]]:
        tree: list[dict[str, Any]] = [
            {"$component": "Checkbox", "$id": "toggle", "checked": self.show_extra,
             "onChange": bind(self, "show_extra", "$0.target.checked")},
        ]
        if self.show_extra:
            tree.append({"$component": "Input", "$id": "extra", "value": ""})
        return tree


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
            "data": {"__bind_value__": True},
        })
        await view.rendered()
        assert len(channel.last_tree) == 2
        assert channel.last_tree[1]["$id"] == "extra"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 单根组件（dict）
# ---------------------------------------------------------------------------

class SingleRootView(View):
    def render(self) -> dict[str, Any]:
        return {"$component": "Button", "$id": "ok", "children": "OK"}


def test_single_root_dict() -> None:
    """render() 返回 dict 应自动包装为 list。"""
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
    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Card", "$id": "card", "$children": [
                {"$component": "Input", "$id": "inner", "value": "nested",
                 "onChange": bind(self, "_dummy", "$0")},
            ]},
        ]

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
        assert inner["onChange"][TAG_KEY] == "handler"
        assert "__bind_value__" in inner["onChange"]["extract"]

    asyncio.run(_test())
