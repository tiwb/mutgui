"""View Declaration 实现 — ViewObservers Extension + @impl。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import mutobj
from mutobj import impl

from .view import View

if TYPE_CHECKING:
    from .viewport import ViewPort


class ViewObservers(mutobj.Extension[View]):
    """追踪一个 View 实例的所有 ViewPort 观察者。"""

    _viewports: list = mutobj.field(default_factory=list)  # list[ViewPort]


@impl(View.render)
def _default_render(self: View) -> list[Any]:
    return []


@impl(View.on_event)
def _default_on_event(self: View, event: dict[str, Any]) -> None:
    pass


@impl(View.invalidate)
def _view_invalidate(self: View) -> None:
    ext = ViewObservers.get(self)
    if ext is not None:
        for vp in ext._viewports:
            vp._schedule_flush()
