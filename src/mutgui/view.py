"""View — 后端驱动 UI 的核心抽象。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import mutobj

if TYPE_CHECKING:
    from .events import Event, EventFilter
    from .viewport import ViewPort


class ViewBlock:
    """View.render() 的返回类型 — 一个 View 的完整 UI 块。"""
    __slots__ = ("items",)

    def __init__(self, items: list[dict[str, Any] | View]):
        super().__init__()
        self.items = items


class View(mutobj.Declaration):
    """mutgui 视图基类。

    应用开发者继承此类，覆盖 render() 描述 UI 应该长什么样。
    框架负责 render -> serialize -> send 循环。
    """

    id: str | int = ""

    def render(self) -> ViewBlock:
        """声明当前 UI 应该长什么样。

        返回 ViewBlock，包含组件列表 (dict | View)。
        列表中可包含子 View 实例，框架自动转换为 $view 协议节点。
        """
        raise NotImplementedError

    async def on_event(self, event: Event) -> bool:
        """统一事件入口。

        默认实现：查找 render 中注册的 EventHandler，调用 handle()。
        子类重写可拦截、预处理、后处理，再 super() 走默认分派。
        返回 True 表示事件已消费。
        """
        raise NotImplementedError

    @property
    def viewport(self) -> ViewPort:
        """当前异步上下文对应的 ViewPort。

        仅在由某个客户端触发的事件处理流程中可用。
        """
        raise NotImplementedError

    async def send_command(self, name: str, /, **args: Any) -> None:
        """通过当前 ViewPort 触发前端命令。"""
        raise NotImplementedError

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        raise NotImplementedError

    def install_event_filter(self, filter: EventFilter) -> None:
        """注册 event filter。filter 在 on_event 之前看到事件。"""
        raise NotImplementedError

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 — 解析 WebSocket 消息，路由到目标 View。"""
        raise NotImplementedError

    def render_viewport(self, wire_tree: list[dict[str, Any]], channel_id: int) -> list[dict[str, Any]]:
        """为指定 viewport 特化 wire tree。

        render() 产出模板树（一次），render_viewport() 在每次 push 时
        为每个 viewport 调用，返回该 viewport 应收到的 wire tree。
        默认原样返回。子类覆写可实现 per-viewport 差异化。
        """
        raise NotImplementedError

    async def rendered(self) -> None:
        """等待 deferred render 完成。如果不 dirty，立即返回。"""
        raise NotImplementedError


from . import _view_impl as _view_impl  # noqa: F401, E402
