"""demo gallery 路由组织测试。"""

from pathlib import Path

from demo.framework import MutguiRoute
from demo.framework._server import _GalleryServer, _gallery_html, DemoCollection
from mutgui import View


def test_gallery_server_parses_examples_and_games_paths() -> None:
    demo_root = Path(__file__).resolve().parents[1] / "demo"
    server = _GalleryServer(demo_root)

    assert server._parse_demo_path("/basic/") == ("examples", "basic", "/")
    assert server._parse_demo_path("/examples/basic/something") == (
        "examples",
        "basic",
        "/something",
    )
    assert server._parse_demo_path("/games/mahjong/") == ("games", "mahjong", "/")
    assert server._parse_demo_path("/games/mahjong/all") == ("games", "mahjong", "/all")


def test_mutgui_route_html_includes_mobile_viewport_meta() -> None:
    route = MutguiRoute("/", View(), title="Demo")
    html = route.get_html()

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html


def test_gallery_html_includes_mobile_viewport_and_tappable_links() -> None:
    html = _gallery_html([
        (DemoCollection("games", "Games", Path("D:\\ai\\mutgui\\demo\\games"), "demo.games"), ["mahjong", "gomoku"]),
    ])

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert 'display: block; padding: 14px 16px;' in html
    assert 'href="/games/mahjong/"' in html
    assert 'href="/games/gomoku/"' in html
