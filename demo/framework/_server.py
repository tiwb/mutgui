"""Gallery 服务器 — 文件扫描、懒加载、直接路由分发。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from mutgui import ViewPort
from mutio.net.server import (
    Server, StaticView, Response, HTMLResponse, RedirectResponse,
    WebSocketConnection, WebSocketDisconnect,
)

from ._channel import WebSocketChannel
from ._routes import MODULE_REGISTRY, MutguiRoute, DemoApp

logger = logging.getLogger("mutgui.demo")


def _init_demo_logging(*, debug: bool = False) -> None:
    """初始化 demo 的最小 stdout logging。"""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)-8s %(name)s: %(message)s",
    )


async def _handle_ws(
    route: MutguiRoute, scope: dict[str, Any], receive: Any, send: Any,
) -> None:
    """共享的 WebSocket → ViewPort 生命周期处理。"""
    from mutio.net._server_impl import _make_ws_connection

    vp: ViewPort | None = None
    try:
        ws = _make_ws_connection(scope, receive, send, {})
        await ws.accept()
        first_message = await ws.receive_json()
        if first_message.get("type") != "mount.attach":
            await ws.close(code=4400, reason="expected mount.attach")
            return
        for message in route.runtime_messages():
            await ws.send_json(message)
        channel = WebSocketChannel(ws)
        vp = ViewPort(route.view, channel)
        await vp.initialize()
        await route.view.rendered()
        while True:
            event = await ws.receive_json()
            await vp.handle_event(event)
    except WebSocketDisconnect as exc:
        logger.debug("Demo WebSocket disconnected: route=%s code=%s", route.path, exc.code)
    except Exception:
        logger.exception("Demo WebSocket error on route %s", route.path)
    finally:
        if vp is not None:
            vp.detach()


def _scan_examples(examples_dir: Path) -> list[str]:
    """扫描 examples 目录下的 .py 文件，返回 demo 名称列表。"""
    names = []
    for f in sorted(examples_dir.iterdir()):
        if f.suffix == ".py" and not f.name.startswith("_"):
            names.append(f.stem)
    return names


def _load_example(name: str, examples_dir: Path) -> list[MutguiRoute]:
    """懒加载 example 模块，返回其 routes。优先从 app.routes，fallback 到 routes。"""
    module_path = examples_dir / f"{name}.py"
    if not module_path.exists():
        return []

    demo_parent = str(examples_dir.parent.parent)
    if demo_parent not in sys.path:
        sys.path.insert(0, demo_parent)

    spec_name = f"demo.examples.{name}"
    if spec_name in sys.modules:
        mod = sys.modules[spec_name]
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location(spec_name, module_path)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec_name] = mod
        spec.loader.exec_module(mod)

    app = getattr(mod, "app", None)
    if isinstance(app, DemoApp):
        return app.routes

    routes = getattr(mod, "routes", None)
    if routes is None:
        return []
    return [r for r in routes if isinstance(r, MutguiRoute)]


def _gallery_html(names: list[str]) -> str:
    """生成 Gallery 首页 HTML。"""
    links = "\n".join(
        f'    <li style="margin: 8px 0;">'
        f'<a href="/{name}/" style="font-size: 16px;">{name}</a></li>'
        for name in names
    )
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mutgui examples</title>
</head>
<body>
  <div style="max-width: 600px; margin: 60px auto; font-family: sans-serif;">
    <h1>mutgui examples</h1>
    <ul style="list-style: none; padding: 0;">
{links}
    </ul>
  </div>
</body>
</html>
"""


def _static_views() -> tuple[type[StaticView], ...]:
    views: list[type[StaticView]] = []
    for index, (path, directory) in enumerate(MODULE_REGISTRY.static_mounts()):
        views.append(type(
            f"_StaticFiles{index}",
            (StaticView,),
            {"path": path, "directory": str(directory)},
        ))
    return tuple(views)


class _GalleryServer(Server):
    """Gallery 服务器 — 懒加载 example，直接分发路由。"""
    host = "127.0.0.1"
    port = 8080
    views = _static_views()

    _examples_dir: Path
    _demo_names: list[str]
    _routes: dict[str, list[MutguiRoute]]

    def __init__(self, examples_dir: Path, *, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._examples_dir = examples_dir
        self._demo_names = _scan_examples(examples_dir)
        self._routes = {}
        super().__init__(host=host, port=port)

    def _ensure_loaded(self, name: str) -> list[MutguiRoute]:
        if name not in self._routes:
            self._routes[name] = _load_example(name, self._examples_dir)
        return self._routes[name]

    def _match_route(self, name: str, sub_path: str) -> MutguiRoute | None:
        normalized = sub_path.rstrip("/") or "/"
        routes = self._ensure_loaded(name)
        for route in routes:
            route_normalized = route.path.rstrip("/") or "/"
            if normalized == route_normalized:
                return route
        return None

    async def route(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        from mutio.net._server_impl import _send_response

        path: str = scope.get("path", "/")
        scope_type = scope.get("type")

        # Gallery 首页
        if path == "/" and scope_type == "http":
            resp = HTMLResponse(_gallery_html(self._demo_names))
            await _send_response(resp, send)
            return

        # 解析 /{name}/...
        parts = path.strip("/").split("/", 1)
        name = parts[0] if parts else ""

        if name not in self._demo_names:
            await super().route(scope, receive, send)
            return

        # 尾斜杠重定向：/basic → /basic/
        if path == f"/{name}" and scope_type == "http":
            resp = RedirectResponse(f"/{name}/", status_code=301)
            await _send_response(resp, send)
            return

        sub_path = "/" + parts[1] if len(parts) > 1 else "/"
        route = self._match_route(name, sub_path)

        if route is None:
            await super().route(scope, receive, send)
            return

        if scope_type == "http":
            resp = HTMLResponse(route.get_html())
            await _send_response(resp, send)
            return

        if scope_type == "websocket":
            await _handle_ws(route, scope, receive, send)
            return

        await super().route(scope, receive, send)


def run_gallery(
    examples_dir: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
) -> None:
    """启动 Gallery 服务器。"""
    _init_demo_logging(debug=debug)
    if examples_dir is None:
        examples_dir = Path(__file__).resolve().parent.parent / "examples"

    print(f"mutgui Gallery: http://{host}:{port}/")
    server = _GalleryServer(examples_dir, host=host, port=port)
    server.run()


def run_single(
    app: DemoApp,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
) -> None:
    """启动单个 DemoApp 服务器。"""
    _init_demo_logging(debug=debug)

    class _SingleServer(Server):
        host = "127.0.0.1"
        port = 8080
        views = _static_views()

        async def route(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
            from mutio.net._server_impl import _send_response, _make_ws_connection

            path: str = scope.get("path", "/")
            scope_type = scope.get("type")

            matched = None
            normalized = path.rstrip("/") or "/"
            for r in app.routes:
                if normalized == (r.path.rstrip("/") or "/"):
                    matched = r
                    break

            if matched is None:
                await super().route(scope, receive, send)
                return

            if scope_type == "http":
                resp = HTMLResponse(matched.get_html())
                await _send_response(resp, send)
                return

            if scope_type == "websocket":
                await _handle_ws(matched, scope, receive, send)
                return

            await super().route(scope, receive, send)

    print(f"mutgui: http://{host}:{port}/")
    server = _SingleServer(host=host, port=port)
    server.run()
