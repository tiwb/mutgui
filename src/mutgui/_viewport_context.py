"""ViewPort 运行时上下文。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .viewport import ViewPort


_current_viewport: ContextVar[ViewPort | None] = ContextVar(
    "mutgui_current_viewport",
    default=None,
)


def set_current_viewport(viewport: ViewPort) -> Token[ViewPort | None]:
    return _current_viewport.set(viewport)


def reset_current_viewport(token: Token[ViewPort | None]) -> None:
    _current_viewport.reset(token)


def get_current_viewport() -> ViewPort | None:
    return _current_viewport.get()
