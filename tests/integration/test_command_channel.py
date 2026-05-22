"""command channel 集成测试。"""

from __future__ import annotations

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback, PerViewport


pytestmark = pytest.mark.integration


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
                "children": PerViewport(lambda vid: f"Connection {vid}"),
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


# ---------------------------------------------------------------------------
# setHash 集成测试
# ---------------------------------------------------------------------------

class SetHashView(View):
    """点击后发送 mutgui.setHash，可控 hash / replace。"""

    def __init__(self, *, hash_value: str, replace: bool = False) -> None:
        super().__init__()
        self.hash_value = hash_value
        self.replace = replace

    def render(self) -> ViewBlock:
        return ViewBlock([
            {
                "$component": "button",
                "$id": "set-hash-btn",
                "data-testid": "set-hash-btn",
                "children": "Set hash",
                "onClick": Callback(self._set_hash),
            },
        ])

    async def _set_hash(self) -> None:
        if self.replace:
            await self.send_command("mutgui.setHash", hash=self.hash_value, replace=True)
        else:
            await self.send_command("mutgui.setHash", hash=self.hash_value)


async def test_set_hash_pushes_history_entry(app, page):
    """setHash 默认 push 模式——URL 变、不刷页、留历史记录。"""
    view = SetHashView(hash_value="#/settings/llm")
    url = app.mount(view)
    await page.goto(url)

    initial_url = page.url
    await page.get_by_test_id("set-hash-btn").click()
    await page.wait_for_function("() => location.hash === '#/settings/llm'")

    # 不刷页：按钮仍可见
    await expect(page.get_by_test_id("set-hash-btn")).to_be_visible()

    # 留了历史记录：back 能返回原 URL
    await page.go_back()
    await page.wait_for_url(initial_url)


async def test_set_hash_replace_does_not_create_history_entry(app, page):
    """setHash replace=True 走 replaceState，不留历史记录。"""
    view = SetHashView(hash_value="#/replaced", replace=True)
    url = app.mount(view)
    await page.goto(url)

    history_before = await page.evaluate("() => history.length")
    await page.get_by_test_id("set-hash-btn").click()
    await page.wait_for_function("() => location.hash === '#/replaced'")
    history_after = await page.evaluate("() => history.length")

    assert history_after == history_before, (
        f"replaceState 不应增加 history 长度 (before={history_before}, after={history_after})"
    )


async def test_set_hash_normalizes_bare_string(app, page):
    """裸串自动补 # 前缀。"""
    view = SetHashView(hash_value="settings")
    url = app.mount(view)
    await page.goto(url)

    await page.get_by_test_id("set-hash-btn").click()
    await page.wait_for_function("() => location.hash === '#settings'")


async def test_set_hash_empty_string_clears_hash(app, page):
    """空串清空 hash，不动 pathname 不刷页。"""
    view = SetHashView(hash_value="")
    url = app.mount(view)
    # 初始带上 hash，验证清空
    await page.goto(url + "#/will-be-cleared")
    pathname_before = await page.evaluate("() => location.pathname")

    await page.get_by_test_id("set-hash-btn").click()
    await page.wait_for_function("() => location.hash === ''")

    pathname_after = await page.evaluate("() => location.pathname")
    assert pathname_after == pathname_before
    # 不刷页：按钮仍在
    await expect(page.get_by_test_id("set-hash-btn")).to_be_visible()
