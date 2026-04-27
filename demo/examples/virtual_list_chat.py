"""VirtualList 聊天流式示例 — 手动验证可变高度与 stick-to-bottom。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterator

import mutobj

from mutgui import View, ViewBlock, Bind, Callback, VirtualList, VirtualListItemAdapter

from demo.framework import MutguiRoute, DemoApp


@dataclass(slots=True)
class ChatMessage:
    uid: int
    role: str
    author: str
    text: str


class ChatMessageView(View):
    message: ChatMessage

    def render(self) -> ViewBlock:
        is_user = self.message.role == "user"
        bubble_style = {
            "maxWidth": "80%",
            "borderRadius": 14,
            "padding": "10px 14px",
            # 用 mutgui token，跟随亮/暗主题自动适配
            "background": "var(--mutgui-accent)" if is_user else "var(--mutgui-surface)",
            "color": "#ffffff" if is_user else "var(--mutgui-text)",
            "boxShadow": "0 1px 3px rgba(0, 0, 0, 0.08)",
            "border": "none" if is_user else "1px solid var(--mutgui-border)",
        }
        meta_style = {
            "fontSize": 12,
            "color": "var(--mutgui-text-dim)",
            "marginBottom": 6,
        }
        content_style = {
            "whiteSpace": "pre-wrap",
            "lineHeight": 1.65,
            "wordBreak": "break-word",
        }
        return ViewBlock([{
            "$component": "div", "$id": "row",
            "style": {
                "display": "flex",
                "justifyContent": "flex-end" if is_user else "flex-start",
                "padding": "6px 0",
            },
            "$children": [
                {"$component": "div", "$id": "bubble", "style": bubble_style,
                 "$children": [
                     {"$component": "div", "$id": "meta", "style": meta_style,
                      "children": self.message.author},
                     {"$component": "div", "$id": "content", "style": content_style,
                      "children": self.message.text or "…"},
                 ]},
            ],
        }])


class ChatAdapter(VirtualListItemAdapter):
    messages: list[ChatMessage] = mutobj.field(default_factory=list)
    _next_uid: int = 0

    def __init__(self) -> None:
        super().__init__()
        self.messages = []
        self._next_uid = 0
        self.reset_demo()

    @property
    def item_count(self) -> int:
        return len(self.messages)

    def item_id(self, index: int) -> str:
        return f"msg-{self.messages[index].uid}"

    def create_item_view(self, index: int) -> View:
        return ChatMessageView(message=self.messages[index])

    def _append_raw(self, role: str, author: str, text: str) -> int:
        uid = self._next_uid
        self._next_uid += 1
        self.messages.append(ChatMessage(uid=uid, role=role, author=author, text=text))
        return uid

    def _find_index(self, uid: int) -> int | None:
        for index, message in enumerate(self.messages):
            if message.uid == uid:
                return index
        return None

    def _invalidate_existing_item(self, uid: int) -> bool:
        item_id = f"msg-{uid}"
        updated = False
        for virtual_list in self.virtual_lists:
            item_view = virtual_list.item_views.get(item_id)
            if item_view is not None:
                item_view.invalidate()
                updated = True
        return updated

    def add_message(self, role: str, text: str) -> int:
        author = "你" if role == "user" else "助手"
        uid = self._append_raw(role, author, text)
        self.invalidate()
        return uid

    def append_to_message(self, uid: int, chunk: str) -> None:
        index = self._find_index(uid)
        if index is None:
            return
        self.messages[index].text += chunk
        if not self._invalidate_existing_item(uid):
            self.invalidate()

    def add_demo_history(self) -> None:
        self.add_message("assistant", (
            "这是专门用来拉高 item 高度的长消息。\n\n"
            "你可以先向上滚动离开底部，再点一次这个按钮，观察列表停留在当前阅读位置；"
            "随后再手动滚到底部，下一次流式输出会恢复自动跟随。\n\n"
            "为了让高度更明显，这里额外补三段内容：\n"
            "1. 可变高度虚拟列表不能再用 index × 固定高度推 offset。\n"
            "2. 单条消息增长时，后续 item 位置必须依赖真实测量结果连续重排。\n"
            "3. 贴底逻辑应该锚到 scrollHeight - clientHeight，而不是最后一项的顶部。"
        ))

    def reset_demo(self) -> None:
        self.messages = []
        seed_messages = [
            ("assistant", "助手", "这是一个聊天型 VirtualList demo。先滚到底，再点“发送并流式回复”。"),
            ("user", "你", "我想验证最后一条消息在流式增长时，会不会持续贴着底部。"),
            ("assistant", "助手", (
                "会的。当前列表启用了 stick_to_bottom=True，且每条消息会在前端通过 "
                "ResizeObserver 自动重测高度。"
            )),
            ("user", "你", "如果我向上滚动去看历史呢？"),
            ("assistant", "助手", (
                "这时跟随会解除。你可以向上滚动后再点“插入超长消息”，"
                "看它是否保持当前位置而不是被强行拉到底。"
            )),
            ("assistant", "助手", (
                "下面这条故意写得更长一些，用来制造不同高度：\n"
                "- 短消息只有一行\n"
                "- 解释型消息会换行\n"
                "- 长段落会形成很高的 item\n\n"
                "只要列表能正确堆叠、滚动条高度会随着测量逐步校正，就说明可变高度路径已经真正打通。"
            )),
        ]
        for role, author, text in seed_messages:
            self._append_raw(role, author, text)
        for virtual_list in self.virtual_lists:
            virtual_list.item_views.clear()
        self.invalidate()


class VirtualListChatView(View):
    def __init__(self) -> None:
        super().__init__()
        self.adapter = ChatAdapter()
        self.chat_list = VirtualList(
            id="chat",
            adapter=self.adapter,
            stick_to_bottom=True,
            estimated_item_height=96,
        )
        self.prompt = "为什么聊天列表不能继续假设所有 item 都是固定高度？"
        self.status = "点击发送后，最后一条助手消息会流式增长；向上滚动后再次触发，可观察解除跟随。"
        self.is_streaming = False
        self._stream_task: asyncio.Task[None] | None = None

    def _build_reply(self, prompt: str) -> str:
        return (
            f"收到问题：{prompt}\n\n"
            "从聊天场景看，固定高度会同时在三处失真：\n"
            "1. 短消息和长 Markdown 的高度差非常大；\n"
            "2. 最后一条消息会随着 token 持续增长；\n"
            "3. 用户是否停留在底部，需要根据真实 scrollHeight 判断。\n\n"
            "因此更稳妥的做法是：未测量项先用估算高度占位，渲染后立刻用真实高度校正；"
            "如果当前处于 FOLLOWING 状态，就把 scrollTop 重新锚到内容底部。"
        )

    def _iter_chunks(self, text: str) -> Iterator[str]:
        step = 18
        for start in range(0, len(text), step):
            yield text[start:start + step]

    def _on_send_and_stream(self) -> None:
        if self.is_streaming:
            self.status = "已有流式回复正在进行中，请稍等当前演示跑完。"
            self.invalidate()
            return

        prompt = self.prompt.strip() or "请给我一段更长的解释，用来测试聊天列表的流式布局。"
        self.adapter.add_message("user", prompt)
        reply_uid = self.adapter.add_message("assistant", "")
        self.prompt = ""
        self.is_streaming = True
        self.status = "正在流式输出。现在向上滚动，可以观察列表从 FOLLOWING 切到 DETACHED。"
        self.invalidate()
        self._stream_task = asyncio.create_task(
            self._run_stream(reply_uid, self._build_reply(prompt)),
        )

    def _on_add_history(self) -> None:
        self.adapter.add_demo_history()
        self.status = "已追加一条超长消息。若你此时不在底部，列表应保持当前阅读位置。"
        self.invalidate()

    def _on_reset(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None
        self.is_streaming = False
        self.prompt = "为什么聊天列表不能继续假设所有 item 都是固定高度？"
        self.adapter.reset_demo()
        self.status = "已重置为初始对话。滚到底部后再次发送，可重复验证跟随效果。"
        self.invalidate()

    async def _run_stream(self, reply_uid: int, text: str) -> None:
        try:
            for chunk in self._iter_chunks(text):
                await asyncio.sleep(0.08)
                self.adapter.append_to_message(reply_uid, chunk)
        except asyncio.CancelledError:
            self.status = "流式回复已取消。"
            self.is_streaming = False
            self.invalidate()
            return

        self.is_streaming = False
        self._stream_task = None
        self.status = "流式回复已完成。你可以向上滚动后再插入超长消息，继续观察 DETACHED 行为。"
        self.invalidate()

    def render(self) -> ViewBlock:
        action_items = [
            {"$component": "antd.Button", "$id": "send",
             "type": "primary", "children": "发送并流式回复",
             "disabled": self.is_streaming,
             "onClick": Callback(self._on_send_and_stream)},
            {"$component": "antd.Button", "$id": "history",
             "children": "插入超长消息",
             "onClick": Callback(self._on_add_history)},
            {"$component": "antd.Button", "$id": "reset",
             "children": "重置",
             "onClick": Callback(self._on_reset)},
        ]
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3,
             "children": "mutgui — VirtualList Chat Stream Demo"},
            {"$component": "antd.Typography.Paragraph", "$id": "intro",
             "children": (
                 "这个示例专门用于手动验证聊天场景：可变高度、最后一条流式增长、"
                 "以及 stick-to-bottom 在用户滚动后的解除/恢复。"
             )},
            {"$component": "antd.Alert", "$id": "status",
              "type": "info", "showIcon": True,
              "style": {"marginBottom": 16},
              "message": f"当前消息数：{self.adapter.item_count}",
              "description": self.status},
            {"$component": "div", "$id": "chat-shell",
              "style": {
                  "height": 560,
                 "display": "flex",
                 "flexDirection": "column",
                 "padding": 12,
                 "border": "1px solid var(--mutgui-border)",
                  "borderRadius": 12,
                  "background": "var(--mutgui-surface)",
              },
              "$children": [self.chat_list]},
            {"$component": "antd.Space", "$id": "composer",
              "direction": "vertical", "size": "middle",
              "style": {"width": "100%", "marginTop": 16},
              "$children": [
                  {"$component": "antd.Input.TextArea", "$id": "prompt",
                  "rows": 3,
                   "value": self.prompt,
                   "placeholder": "输入一条问题，然后点击发送并流式回复",
                   "onChange": Bind(self, "prompt", "$0.target.value")},
                  {"$component": "div", "$id": "actions",
                   "style": {"display": "flex", "gap": "8px", "flexWrap": "wrap",
                             "justifyContent": "flex-end"},
                   "$children": action_items},
              ]},
        ])


app = DemoApp([
    MutguiRoute("/", VirtualListChatView(), title="VirtualList Chat Stream"),
])


if __name__ == "__main__":
    app.run()
