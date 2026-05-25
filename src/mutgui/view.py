"""View — 后端驱动 UI 的核心抽象。

定义了 View 声明、ViewBlock 返回类型、以及 Render* 类型体系
（View.render() 产出的组件树类型，含尚未序列化的 View/EventHandler）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TYPE_CHECKING, TypeAlias, Union

import mutobj


if TYPE_CHECKING:
    from .events import Event, EventFilter, EventHandler
    from .viewport import ViewPort

# 设计要点：value 联合用协变的 Sequence/Mapping，具体容器用 list/dict。
# 这样既能在 "流转" 侧让 list[dict[str, WireValue]] ⊆ WireValue（绕过 list 不变性），
# 又能在 "构建" 侧保留可写的 list[WireValue]/dict[str, WireValue] 具体类型。

WireValue: TypeAlias = None | bool | int | float | str | Sequence["WireValue"] | Mapping[str, "WireValue"]
WireNode: TypeAlias = dict[str, "WireValue"]
WireTree: TypeAlias = list[WireNode]

RenderValue: TypeAlias = (
    None | bool | int | float | str
    | "View" | "EventHandler" | "PerViewport"
    | Sequence["RenderValue"] | Mapping[str, "RenderValue"]
)
RenderComponent: TypeAlias = dict[str, RenderValue]
RenderNode: TypeAlias = Union[RenderComponent, "View", "PerViewport"]
RenderTree: TypeAlias = list[RenderNode]

ViewId: TypeAlias = str | int


class PerViewport(mutobj.Declaration):
    """Per-viewport 值原语。类似 Callback 的参数捕获语义。

    标记需要在不同 viewport 下取不同内容的位置。可出现在 dict 值位、
    list 元素位等任意 RenderValue 位置。
    """

    def __init__(
        self, fn: Callable[..., "RenderValue"], /, *args: Any, **kwargs: Any,
    ) -> None:
        """创建 PerViewport。

        fn 签名：``fn(viewport_id: int, *args, **kwargs) -> RenderValue``
        viewport_id 始终作为第一个位置参数注入。
        *args / **kwargs 在构造期捕获，求值时原样 forward。
        """
        ...

    def get(self, viewport_id: int) -> "RenderValue":
        """按 viewport_id 取值。"""
        ...


class ViewBlock:
    """View.render() 的返回类型 — 一个 View 的完整 UI 块。"""
    __slots__ = ("items",)

    def __init__(self, items: RenderTree):
        super().__init__()
        self.items = items


class View(mutobj.Declaration):
    """mutgui 视图基类。

    应用开发者继承此类，覆盖 render() 描述 UI 应该长什么样。
    框架负责 render -> serialize -> send 循环。
    """

    id: ViewId = ""

    def render(self) -> ViewBlock:
        """声明当前 UI 应该长什么样。

        返回 ViewBlock，包含组件列表 (dict | View)。
        列表中可包含子 View 实例，框架自动转换为 $view 协议节点。
        """
        ...

    async def on_event(self, event: Event) -> bool:
        """统一事件入口。

        默认实现：查找 render 中注册的 EventHandler，调用 handle()。
        子类重写可拦截、预处理、后处理，再 super() 走默认分派。
        返回 True 表示事件已消费。
        """
        ...

    @property
    def viewport(self) -> ViewPort:
        """当前异步上下文对应的 ViewPort。

        仅在由某个客户端触发的事件处理流程中可用。
        """
        ...

    async def send_command(self, name: str, /, **args: Any) -> None:
        """通过当前 ViewPort 触发前端命令。"""
        ...

    async def broadcast_command(self, name: str, /, **args: Any) -> None:
        """向所有观察此 View 的 ViewPort 广播命令。

        与 send_command 的差异：

        - send_command：仅当前 ViewPort（事件触发那个 tab）—— 适合 ViewPort
          私有状态（滚动位置、focus、动画触发、toast 等）。要求当前异步
          上下文存在 ViewPort。
        - broadcast_command：所有观察此 View 的 ViewPort —— 适合 View 级
          共享状态（URL hash、跨 tab 同步的客户端状态）。**不**要求当前
          上下文存在 ViewPort，可在后台任务、定时器、agent 事件回调中调用。

        单个 ViewPort 发送失败（断连等）不影响其他 ViewPort。
        无观察者时静默 no-op。
        """
        ...

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        ...

    def install_event_filter(self, filter: EventFilter) -> None:
        """注册 event filter。filter 在 on_event 之前看到事件。"""
        ...

    @property
    def active_viewport_ids(self) -> Sequence[int]:
        """当前观察此 View 的所有活跃 viewport（channel）id 列表。

        在 render() 内部使用，配合 PerViewport 主动构造 per-VP 内容。
        无活跃 viewport 时返回空列表。顺序未排序。
        """
        ...

    async def rendered(self) -> None:
        """等待 deferred render 完成。如果不 dirty，立即返回。"""
        ...


from . import _view_impl as _view_impl  # noqa: F401, E402
