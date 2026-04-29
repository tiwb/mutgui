"""command channel 集成测试。"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback


pytestmark = pytest.mark.integration


def _replace_children(
    tree: list[dict[str, object]],
    node_id: str,
    children: str,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for node in tree:
        copied = dict(node)
        if copied.get("$id") == node_id:
            copied["children"] = children
        raw_children = copied.get("$children")
        if isinstance(raw_children, list):
            nested: list[object] = []
            for child in raw_children:
                if isinstance(child, dict):
                    nested.extend(_replace_children([child], node_id, children))
                else:
                    nested.append(child)
            copied["$children"] = nested
        result.append(copied)
    return result


class CommandChannelView(View):
    def __init__(self, *, redirect_url: str) -> None:
        super().__init__()
        self.redirect_url = redirect_url

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


class HistoryTargetView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "div",
                "$id": "target-title",
                "data-testid": "target-title",
                "children": "Redirect target",
            },
            {
                "$component": "button",
                "$id": "history-back-btn",
                "data-testid": "history-back-btn",
                "children": "History back",
                "onClick": Callback(self._history_back),
            },
        ])

    async def _history_back(self) -> None:
        await self.send_command("mutgui.history", delta=-1)


class ReloadView(View):
    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "div",
                "$id": "connection-id",
                "data-testid": "connection-id",
                "children": "Connection pending",
            },
            {
                "$component": "button",
                "$id": "reload-btn",
                "data-testid": "reload-btn",
                "children": "Reload",
                "onClick": Callback(self._reload),
            },
        ])

    async def _reload(self) -> None:
        await self.send_command("mutgui.reload")

    def render_viewport(
        self,
        wire_tree: list[dict[str, object]],
        channel_id: int,
    ) -> list[dict[str, object]]:
        return _replace_children(wire_tree, "connection-id", f"Connection {channel_id}")


async def test_command_redirect_and_history(app, page):
    target = HistoryTargetView()
    target_url = app.mount(target, "command-target")
    source = CommandChannelView(redirect_url=target_url)
    source_url = app.mount(source, "command-source")

    await page.goto(source_url)

    await page.get_by_test_id("redirect-btn").click()
    await page.wait_for_url(target_url)
    await expect(page.get_by_test_id("target-title")).to_have_text("Redirect target")

    await page.get_by_test_id("history-back-btn").click()
    await page.wait_for_url(source_url)
    await expect(page.get_by_test_id("redirect-btn")).to_be_visible()


async def test_command_reload_refreshes_current_page(app, page):
    view = ReloadView()
    url = app.mount(view, "reload-view")

    await page.goto(url)
    before = await page.get_by_test_id("connection-id").text_content()
    assert before is not None

    await page.get_by_test_id("reload-btn").click()
    await expect(page.get_by_test_id("connection-id")).not_to_have_text(before)


async def test_unknown_command_warns_without_crashing(app, page):
    view = CommandChannelView(redirect_url="about:blank#mutgui-command-redirected")
    url = app.mount(view)
    await page.goto(url)

    async with page.expect_console_message(
        lambda msg: msg.type == "warning" and "Unknown command: mutgui.missing" in msg.text,
    ):
        await page.get_by_test_id("missing-btn").click()

    await expect(page.get_by_test_id("missing-btn")).to_be_visible()
