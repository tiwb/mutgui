"""command channel 集成测试。"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback


pytestmark = pytest.mark.integration


class CommandChannelView(View):
    def __init__(self) -> None:
        super().__init__()
        self.redirect_url = "about:blank#mutgui-command-redirected"

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "button",
                "$id": "redirect-btn",
                "data-testid": "redirect-btn",
                "children": "Redirect",
                "onClick": Callback(self._redirect),
            },
            {
                "$component": "button",
                "$id": "missing-btn",
                "data-testid": "missing-btn",
                "children": "Unknown command",
                "onClick": Callback(self._missing),
            },
        ])

    async def _redirect(self) -> None:
        await self.send_command("mutgui.redirect", url=self.redirect_url)

    async def _missing(self) -> None:
        await self.send_command("mutgui.missing", value=1)


async def test_command_redirect(app, page):
    view = CommandChannelView()
    url = app.mount(view)
    await page.goto(url)

    await page.get_by_test_id("redirect-btn").click()
    await page.wait_for_url("about:blank#mutgui-command-redirected")
    assert page.url == "about:blank#mutgui-command-redirected"


async def test_unknown_command_warns_without_crashing(app, page):
    view = CommandChannelView()
    url = app.mount(view)
    await page.goto(url)

    async with page.expect_console_message(
        lambda msg: msg.type == "warning" and "Unknown command: mutgui.missing" in msg.text,
    ):
        await page.get_by_test_id("missing-btn").click()

    await expect(page.get_by_test_id("missing-btn")).to_be_visible()
