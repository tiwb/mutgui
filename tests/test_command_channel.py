"""command channel 单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewBlock, ViewPort, Channel, Callback


class MockChannel(Channel):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class CommandView(View):
    def __init__(self) -> None:
        super().__init__()
        self.clicks = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "button",
                "$id": "send",
                "children": f"Clicks: {self.clicks}",
                "onClick": Callback(self._on_click),
            },
        ])

    async def _on_click(self) -> None:
        self.clicks += 1
        await self.send_command(
            "mutgui.redirect",
            url=f"https://example.com/{self.clicks}",
            replace=(self.clicks % 2 == 0),
        )
        self.invalidate()


class ChildCommandView(View):
    id = "child"

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "button",
                "$id": "child-send",
                "children": "Child command",
                "onClick": Callback(self._on_click),
            },
        ])

    async def _on_click(self) -> None:
        await self.viewport.send_command(
            "mutgui.redirect",
            url="https://example.com/child",
        )


class ParentView(View):
    def __init__(self) -> None:
        super().__init__()
        self.child = ChildCommandView()

    def render(self) -> ViewBlock:
        return ViewBlock([self.child])


def test_viewport_send_command_writes_wire_message() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = CommandView()
        vp = ViewPort(view, channel)

        await vp.send_command(
            "mutgui.redirect",
            url="https://example.com",
            replace=True,
        )

        assert channel.messages == [{
            "type": "command",
            "viewId": [],
            "name": "mutgui.redirect",
            "args": {"url": "https://example.com", "replace": True},
        }]

    asyncio.run(_test())


def test_view_can_send_command_in_current_viewport_context() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = ParentView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()
        channel.messages.clear()

        await vp.handle_event({
            "source": ["child", "child-send"],
            "event": "onClick",
            "data": {},
        })

        assert channel.messages == [{
            "type": "command",
            "viewId": ["child"],
            "name": "mutgui.redirect",
            "args": {"url": "https://example.com/child"},
        }]

    asyncio.run(_test())


def test_command_messages_keep_order_and_do_not_break_render_flow() -> None:
    async def _test() -> None:
        channel = MockChannel()
        view = CommandView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()
        channel.messages.clear()

        await vp.handle_event({
            "source": ["send"],
            "event": "onClick",
            "data": {},
        })
        await view.rendered()

        assert [msg["type"] for msg in channel.messages] == ["command", "render"]
        assert channel.messages[0]["args"] == {
            "url": "https://example.com/1",
            "replace": False,
        }
        assert channel.messages[1]["tree"][0]["children"] == "Clicks: 1"

        channel.messages.clear()
        await vp.send_command("mutgui.redirect", url="https://example.com/a")
        await vp.send_command("mutgui.redirect", url="https://example.com/b")

        assert [msg["args"]["url"] for msg in channel.messages] == [
            "https://example.com/a",
            "https://example.com/b",
        ]

    asyncio.run(_test())


def test_command_messages_are_not_replayed_on_invalidate_or_new_viewport() -> None:
    async def _test() -> None:
        view = CommandView()

        channel_a = MockChannel()
        vp_a = ViewPort(view, channel_a)
        await vp_a.initialize()
        await view.rendered()
        channel_a.messages.clear()

        await vp_a.send_command("mutgui.redirect", url="https://example.com/once")
        assert [msg["type"] for msg in channel_a.messages] == ["command"]

        channel_a.messages.clear()
        view.invalidate()
        await view.rendered()
        assert channel_a.messages
        assert all(msg["type"] == "render" for msg in channel_a.messages)

        channel_b = MockChannel()
        vp_b = ViewPort(view, channel_b)
        await vp_b.initialize()
        await view.rendered()
        assert channel_b.messages
        assert all(msg["type"] == "render" for msg in channel_b.messages)

    asyncio.run(_test())
