"""hash_nav demo — 后端用 mutgui.setHash 改 URL，浏览器原生 hashchange 回传成 $hashchange 事件。

与 `command.py` 的对照：
- `command.py` 演示「整页导航命令」（redirect / history / reload）：每次都换 pathname，
  浏览器重新拉 HTML，WebSocket 断开重连，channel_id 会变。
- 本 demo 演示「页内 hash 路由」原语：单 ViewPort、单 WebSocket、不重连，所有「分段」
  在同一个 View 里靠 hash 切换；后端通过 `mutgui.setHash` 改 URL，浏览器 back/前进 /
  手动改地址栏 hash 通过 `$hashchange` 事件回传后端。

三条肉眼验收路径：
1. 防循环：点 [Section B] → 地址栏变 `#/section/b`，事件日志不新增（setHash 不触发 hashchange）。
2. 双向：浏览器后退 → 日志多一条 `cause=user, prev=#/section/b, now=#/section/a`。
3. 首屏握手：新 tab 直接打开 `/#/section/c` → 进入 C 段，日志首条 `cause=initial, prev=null`。
"""

from __future__ import annotations

from typing import Any

import mutobj

from mutgui import View, ViewBlock, Callback, PerViewport, Event

from demo.framework import MutguiRoute, DemoApp


_LOG_LIMIT = 12


def _replace_children(
    tree: list[dict[str, object]],
    node_id: str,
    children: str,
) -> list[dict[str, object]]:
    """递归把 `$id == node_id` 节点的 children 字段替换为给定字符串。"""
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


_SECTION_BODIES: dict[str, tuple[str, str]] = {
    "a": ("Section A", "这是 A 段。试试点 B / C，或者按浏览器后退键。"),
    "b": ("Section B", "这是 B 段。注意：地址栏变了但下面日志不会新增——setHash 不触发 hashchange。"),
    "c": ("Section C", "这是 C 段。复制当前 URL 到新 tab 打开，应能直达 C 段（首屏握手 cause=initial）。"),
}


class HashNavView(View):
    """单 View 内的 hash 路由 demo。"""
    _hash: str = ""
    _log: list[dict[str, Any]] = mutobj.field(default_factory=list)

    def __init__(self) -> None:
        super().__init__()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    async def on_event(self, event: Event) -> bool:
        if event.component_id == "" and event.name == "$hashchange":
            data = event.kwargs
            entry = {
                "cause": data.get("cause", "?"),
                "previousHash": data.get("previousHash"),
                "hash": data.get("hash", ""),
            }
            self._log.insert(0, entry)
            del self._log[_LOG_LIMIT:]
            self._hash = entry["hash"] or ""
            self.invalidate()
            return True
        return await super().on_event(event)

    # ------------------------------------------------------------------
    # 后端按钮 → mutgui.setHash 命令
    # ------------------------------------------------------------------

    async def _goto_a(self) -> None:
        self._hash = "#/section/a"
        self.invalidate()
        await self.send_command("mutgui.setHash", hash="#/section/a")

    async def _goto_b(self) -> None:
        self._hash = "#/section/b"
        self.invalidate()
        await self.send_command("mutgui.setHash", hash="#/section/b")

    async def _goto_c(self) -> None:
        self._hash = "#/section/c"
        self.invalidate()
        await self.send_command("mutgui.setHash", hash="#/section/c")

    async def _replace_to_a(self) -> None:
        self._hash = "#/section/a"
        self.invalidate()
        await self.send_command("mutgui.setHash", hash="#/section/a", replace=True)

    async def _clear_hash(self) -> None:
        self._hash = ""
        self.invalidate()
        await self.send_command("mutgui.setHash", hash="")

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def _section_block(self) -> dict[str, object]:
        # 从 hash 解析当前段。约定 hash 形如 "#/section/<key>"，其它一律视为「未选中」。
        key = ""
        if self._hash.startswith("#/section/"):
            key = self._hash[len("#/section/"):].strip("/").lower()
        if key in _SECTION_BODIES:
            title, body = _SECTION_BODIES[key]
        else:
            title = "（未选中分段）"
            body = "当前 hash 不匹配任何 section。点上面的按钮，或手动在地址栏输 #/section/a 试试。"
        return {
            "$component": "div",
            "$id": "section",
            "style": {
                "padding": "16px",
            },
            "$children": [
                {"$component": "h3", "$id": "section-title",
                 "style": {"margin": "0 0 8px 0"}, "children": title},
                {"$component": "p", "$id": "section-body",
                 "style": {"margin": "0"}, "children": body},
            ],
        }

    def _log_block(self) -> dict[str, object]:
        if not self._log:
            rows: list[dict[str, object]] = [{
                "$component": "li",
                "$id": "log-empty",
                "style": {"fontStyle": "italic"},
                "children": "（暂无 $hashchange 事件——首屏握手会自动产生一条 cause=initial）",
            }]
        else:
            rows = []
            for idx, entry in enumerate(self._log):
                prev = entry["previousHash"]
                prev_repr = "null" if prev is None else f'"{prev}"'
                cause = entry["cause"]
                line = (
                    f'[{cause}]  prev={prev_repr}  →  now="{entry["hash"]}"'
                )
                rows.append({
                    "$component": "li",
                    "$id": f"log-{idx}",
                    "style": {
                        "fontFamily": "ui-monospace, monospace",
                        "fontSize": "13px",
                        "padding": "4px 0",
                    },
                    "children": line,
                })
        return {
            "$component": "div",
            "$id": "log-wrap",
            "$children": [
                {"$component": "h3", "$id": "log-title",
                 "style": {"margin": "0 0 8px 0", "fontSize": "16px"},
                 "children": "$hashchange 事件日志（最新在上）"},
                {"$component": "ul", "$id": "log-list",
                 "style": {"listStyle": "none", "padding": "0", "margin": "0"},
                 "$children": rows},
            ],
        }

    def render(self) -> ViewBlock:
        button_style = {
            "padding": "6px 14px",
            "fontSize": "14px",
            "cursor": "pointer",
        }

        return ViewBlock([
            {
                "$component": "div",
                "$id": "wrap",
                "style": {
                    "padding": "24px",
                    "fontFamily": "system-ui",
                    "maxWidth": "760px",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "14px",
                },
                "$children": [
                    {"$component": "h2", "$id": "title", "children": "Hash Navigation Demo"},
                    {
                        "$component": "p",
                        "$id": "desc",
                        "style": {"margin": "0"},
                        "children": (
                            "演示 mutgui.setHash 命令 + $hashchange 事件这对 SPA 路由原语。"
                            "和 command demo（整页 redirect/history/reload）形成对照——这里 WebSocket 不会断。"
                        ),
                    },
                    {
                        "$component": "div",
                        "$id": "status",
                        "style": {
                            "display": "flex",
                            "flexDirection": "column",
                            "gap": "4px",
                            "padding": "10px 12px",
                            "fontFamily": "ui-monospace, monospace",
                            "fontSize": "13px",
                        },
                        "$children": [
                            {"$component": "div", "$id": "status-hash",
                             "children": f'后端持有的 hash：{self._hash!r}'},
                            {"$component": "div", "$id": "connection-id",
                             "children": PerViewport(lambda vid: f"当前连接 channel_id：{vid}")},
                            {"$component": "div", "$id": "status-hint",
                             "children": "channel_id 切换不同 section 时不变 → WebSocket 没有重连。"},
                        ],
                    },
                    {
                        "$component": "div",
                        "$id": "actions",
                        "style": {
                            "display": "flex",
                            "flexWrap": "wrap",
                            "gap": "8px",
                        },
                        "$children": [
                            {"$component": "button", "$id": "btn-a",
                             "children": "Section A (push)", "style": button_style,
                             "onClick": Callback(self._goto_a)},
                            {"$component": "button", "$id": "btn-b",
                             "children": "Section B (push)", "style": button_style,
                             "onClick": Callback(self._goto_b)},
                            {"$component": "button", "$id": "btn-c",
                             "children": "Section C (push)", "style": button_style,
                             "onClick": Callback(self._goto_c)},
                            {"$component": "button", "$id": "btn-replace-a",
                             "children": "→ A (replace)", "style": button_style,
                             "onClick": Callback(self._replace_to_a)},
                            {"$component": "button", "$id": "btn-clear",
                             "children": "清空 hash", "style": button_style,
                             "onClick": Callback(self._clear_hash)},
                        ],
                    },
                    self._section_block(),
                    {
                        "$component": "ol",
                        "$id": "verify",
                        "style": {"margin": "0", "paddingLeft": "20px",
                                  "fontSize": "14px"},
                        "$children": [
                            {"$component": "li", "$id": "v1",
                             "children": "防循环：点 Section B，地址栏变了但日志不会新增。"},
                            {"$component": "li", "$id": "v2",
                             "children": "双向：按浏览器后退键，日志会出现 cause=user 一条。"},
                            {"$component": "li", "$id": "v3",
                             "children": "首屏握手：复制当前 URL 到新 tab 打开，日志首条会是 cause=initial。"},
                            {"$component": "li", "$id": "v4",
                             "children": "replace：点「→ A (replace)」后再后退，会跳过那一步（覆盖了历史记录）。"},
                        ],
                    },
                    self._log_block(),
                ],
            },
        ])

app = DemoApp([
    MutguiRoute("/", HashNavView(), title="Hash Navigation", layout="plain"),
])


if __name__ == "__main__":
    app.run()
