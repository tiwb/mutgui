"""theming demo 测试。"""

import asyncio
from typing import Any

from mutgui import Channel, ViewPort

from demo.examples.theming import ThemingDemoView, ThemingRoute


class MockChannel(Channel):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


def test_theming_route_installs_dark_only_when_enabled() -> None:
    view = ThemingDemoView()
    route = ThemingRoute("/", view, title="Theming")

    assert all(msg.get("module") != "@mutgui/theme-dark" for msg in route.runtime_messages())

    view.theme_mode = "dark"
    assert any(
        msg.get("type") == "runtime.install" and msg.get("module") == "@mutgui/theme-dark"
        for msg in route.runtime_messages()
    )


def test_theming_buttons_switch_backend_state_and_request_reload() -> None:
    async def _test() -> None:
        view = ThemingDemoView()
        channel = MockChannel()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()
        channel.messages.clear()

        await vp.handle_event({
            "source": ["use-dark"],
            "event": "onClick",
            "data": {},
        })

        assert view.theme_mode == "dark"
        assert channel.messages == [{
            "type": "command",
            "viewId": [],
            "name": "mutgui.reload",
            "args": {},
        }]

        channel.messages.clear()
        await vp.handle_event({
            "source": ["use-none"],
            "event": "onClick",
            "data": {},
        })

        assert view.theme_mode == "none"
        assert channel.messages == [{
            "type": "command",
            "viewId": [],
            "name": "mutgui.reload",
            "args": {},
        }]

    asyncio.run(_test())
