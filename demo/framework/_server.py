"""Gallery 服务器 — 文件扫描、懒加载、直接路由分发。"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DemoCollection:
    slug: str
    title: str
    directory: Path
    package: str


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
        client = first_message.get("client") if isinstance(first_message.get("client"), dict) else None
        for message in route.runtime_messages():
            await ws.send_json(message)
        channel = WebSocketChannel(ws)
        vp = ViewPort(route.view, channel, _client=client)
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


def _scan_demos(directory: Path) -> list[str]:
    """扫描目录下的 .py 文件，返回 demo 名称列表。"""
    names = []
    if not directory.exists():
        return names
    for f in sorted(directory.iterdir()):
        if f.suffix == ".py" and not f.name.startswith("_"):
            names.append(f.stem)
    return names


def _load_demo(name: str, collection: DemoCollection) -> list[MutguiRoute]:
    """懒加载 demo 模块，返回其 routes。优先从 app.routes，fallback 到 routes。"""
    module_path = collection.directory / f"{name}.py"
    if not module_path.exists():
        return []

    demo_parent = str(collection.directory.parent.parent)
    if demo_parent not in sys.path:
        sys.path.insert(0, demo_parent)

    spec_name = f"{collection.package}.{name}"
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


def _demo_href(collection: DemoCollection, name: str) -> str:
    return f"/{collection.slug}/{name}/"


def _gallery_html(collections: list[tuple[DemoCollection, list[str]]]) -> str:
    """生成 Gallery 首页 HTML。"""
    sections: list[str] = []
    for collection, names in collections:
        if not names:
            continue
        links = "\n".join(
            f'        <li style="margin: 10px 0;">'
            f'<a href="{_demo_href(collection, name)}" '
            f'style="display: block; padding: 14px 16px; border: 1px solid #d9d9d9; border-radius: 12px; '
            f'font-size: 18px; color: inherit; text-decoration: none; background: #fff;">{name}</a></li>'
            for name in names
        )
        sections.append(f"""    <section style="margin-top: 28px;">
      <h2 style="margin: 0 0 12px 0; font-size: 20px;">{collection.title}</h2>
      <ul style="list-style: none; padding: 0; margin: 0;">
{links}
      </ul>
    </section>""")
    sections_html = "\n".join(sections)
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mutgui demos</title>
</head>
<body style="margin: 0; background: #fafafa;">
  <div style="max-width: 680px; margin: 0 auto; padding: 20px 14px 40px; font-family: sans-serif;">
    <h1 style="margin: 0 0 8px 0; font-size: 28px;">mutgui demos</h1>
    <div style="color: #666; font-size: 14px;">选择一个 demo 进入。手机上可直接整块点击。</div>
{sections_html}
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
    """Gallery 服务器 — 懒加载 examples/games，直接分发路由。"""
    host = "127.0.0.1"
    port = 8080
    views = _static_views()

    _collections: dict[str, DemoCollection]
    _demo_names: dict[str, list[str]]
    _routes: dict[tuple[str, str], list[MutguiRoute]]

    def __init__(self, demo_root: Path, *, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._collections = {
            "examples": DemoCollection(
                slug="examples",
                title="Examples",
                directory=demo_root / "examples",
                package="demo.examples",
            ),
            "games": DemoCollection(
                slug="games",
                title="Games",
                directory=demo_root / "games",
                package="demo.games",
            ),
        }
        self._demo_names = {
            slug: _scan_demos(collection.directory)
            for slug, collection in self._collections.items()
        }
        self._routes = {}
        super().__init__(host=host, port=port)

    def _ensure_loaded(self, collection_slug: str, name: str) -> list[MutguiRoute]:
        key = (collection_slug, name)
        if key not in self._routes:
            collection = self._collections[collection_slug]
            self._routes[key] = _load_demo(name, collection)
        return self._routes[key]

    def _match_route(self, collection_slug: str, name: str, sub_path: str) -> MutguiRoute | None:
        normalized = sub_path.rstrip("/") or "/"
        routes = self._ensure_loaded(collection_slug, name)
        for route in routes:
            route_normalized = route.path.rstrip("/") or "/"
            if normalized == route_normalized:
                return route
        return None

    def _parse_demo_path(self, path: str) -> tuple[str, str, str] | None:
        parts = [part for part in path.strip("/").split("/") if part]
        if not parts:
            return None

        if parts[0] in self._collections:
            collection_slug = parts[0]
            if len(parts) < 2:
                return None
            name = parts[1]
            sub_parts = parts[2:]
        else:
            collection_slug = "examples"
            name = parts[0]
            sub_parts = parts[1:]

        if name not in self._demo_names.get(collection_slug, []):
            return None

        sub_path = "/" + "/".join(sub_parts) if sub_parts else "/"
        return collection_slug, name, sub_path

    async def route(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        from mutio.net._server_impl import _send_response

        path: str = scope.get("path", "/")
        scope_type = scope.get("type")

        # Gallery 首页
        if path == "/" and scope_type == "http":
            resp = HTMLResponse(_gallery_html([
                (self._collections["examples"], self._demo_names["examples"]),
                (self._collections["games"], self._demo_names["games"]),
            ]))
            await _send_response(resp, send)
            return

        parsed = self._parse_demo_path(path)
        if parsed is None:
            await super().route(scope, receive, send)
            return

        collection_slug, name, sub_path = parsed
        normalized = path.rstrip("/")

        if sub_path == "/" and scope_type == "http" and path != "/" and path == normalized:
            resp = RedirectResponse(f"{path}/", status_code=301)
            await _send_response(resp, send)
            return

        route = self._match_route(collection_slug, name, sub_path)

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
    demo_root: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
) -> None:
    """启动 Gallery 服务器。"""
    _init_demo_logging(debug=debug)
    if demo_root is None:
        demo_root = Path(__file__).resolve().parent.parent

    print(f"mutgui Gallery: http://{host}:{port}/")
    server = _GalleryServer(demo_root, host=host, port=port)
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
