"""mahjong demo 测试。"""

import asyncio
from typing import Any

import mutobj

from mutgui import Channel, ViewPort

from demo.games.mahjong import Seat, MahjongGame, Meld, PlayerView, TableView, all_view, app


class MockChannel(Channel):
    messages: list[dict[str, Any]] = mutobj.field(default_factory=list)

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


def make_game() -> MahjongGame:
    game = MahjongGame()
    for seat in Seat:
        game.hands[seat] = []
        game.discards[seat] = []
        game.melds[seat] = []
    game.wall = ["9m", "9s", "9p", "5p"]
    game.hint = (Seat.EAST, "draw")
    game.last_discard = None
    game.active_draw = None
    game.winner = None
    return game


def test_draw_and_discard_flow_updates_hint_and_last_discard() -> None:
    game = make_game()
    game.hands[Seat.EAST] = ["1m"] * 13
    game.hands[Seat.SOUTH] = ["2m"] * 13

    assert game.can_draw(Seat.EAST) is True
    assert game.can_draw(Seat.SOUTH) is False

    assert game.draw(Seat.EAST) == "9m"
    assert game.hint == (Seat.EAST, "discard")
    assert game.active_draw == (Seat.EAST, "9m")
    assert game.last_discard is None

    assert game.discard(Seat.EAST, "9m") is True
    assert game.discards[Seat.EAST] == ["9m"]
    assert game.last_discard == (Seat.EAST, "9m")
    assert game.hint == (Seat.SOUTH, "draw")
    assert game.can_draw(Seat.SOUTH) is True

    assert game.draw(Seat.SOUTH) == "9s"
    assert game.last_discard is None
    assert game.hint == (Seat.SOUTH, "discard")


def test_pong_claim_removes_last_discard_and_switches_to_discard_phase() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = ["5m", "5m", "1m"]
    game.discards[Seat.EAST] = ["5m"]
    game.last_discard = (Seat.EAST, "5m")
    game.hint = (Seat.SOUTH, "draw")

    assert game.can_pong(Seat.SOUTH) is True
    assert game.can_pong(Seat.EAST) is False

    assert game.pong(Seat.SOUTH) is True
    assert game.last_discard is None
    assert game.discards[Seat.EAST] == []
    assert game.hands[Seat.SOUTH] == ["1m"]
    assert game.melds[Seat.SOUTH] == [Meld("pong", ("5m", "5m", "5m"), Seat.EAST)]
    assert game.hint == (Seat.SOUTH, "discard")


def test_chi_requires_next_seat_and_valid_sequence() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = ["1m", "2m", "7p"]
    game.hands[Seat.WEST] = ["1m", "2m", "7p"]
    game.discards[Seat.EAST] = ["3m"]
    game.last_discard = (Seat.EAST, "3m")
    game.hint = (Seat.SOUTH, "draw")

    assert game.can_chi(Seat.SOUTH, ["1m", "2m"]) is True
    assert game.can_chi(Seat.SOUTH, ["1m", "7p"]) is False
    assert game.can_chi(Seat.WEST, ["1m", "2m"]) is False

    assert game.chi(Seat.SOUTH, "1m", "2m") is True
    assert game.melds[Seat.SOUTH] == [Meld("chi", ("1m", "2m", "3m"), Seat.EAST)]
    assert game.discards[Seat.EAST] == []
    assert game.hands[Seat.SOUTH] == ["7p"]
    assert game.hint == (Seat.SOUTH, "discard")


def test_chi_options_lists_all_valid_choices() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = ["1m", "2m", "2m", "4m", "4m", "5m"]
    game.discards[Seat.EAST] = ["3m"]
    game.last_discard = (Seat.EAST, "3m")
    game.hint = (Seat.SOUTH, "draw")

    assert game.chi_options(Seat.SOUTH) == [("1m", "2m"), ("2m", "4m"), ("4m", "5m")]


def test_kong_supports_exposed_and_concealed_cases() -> None:
    exposed = make_game()
    exposed.hands[Seat.SOUTH] = ["7p", "7p", "7p", "1m"]
    exposed.discards[Seat.EAST] = ["7p"]
    exposed.last_discard = (Seat.EAST, "7p")
    exposed.hint = (Seat.SOUTH, "draw")

    assert exposed.can_kong(Seat.SOUTH, None) is True
    assert exposed.kong(Seat.SOUTH, None) is True
    assert exposed.discards[Seat.EAST] == []
    assert exposed.melds[Seat.SOUTH] == [Meld("kong", ("7p", "7p", "7p", "7p"), Seat.EAST)]
    assert exposed.active_draw == (Seat.SOUTH, "9m")
    assert exposed.hint == (Seat.SOUTH, "discard")

    concealed = make_game()
    concealed.hands[Seat.SOUTH] = ["2s", "2s", "2s", "2s", "1m"]
    concealed.hint = (Seat.SOUTH, "discard")

    assert concealed.can_concealed_kong(Seat.SOUTH, "2s") is True
    assert concealed.kong(Seat.SOUTH, "2s") is True
    assert concealed.melds[Seat.SOUTH] == [
        Meld("kong", ("2s", "2s", "2s", "2s"), None, concealed=True),
    ]
    assert concealed.active_draw == (Seat.SOUTH, "9m")


def test_hu_requires_basic_winning_shape_for_discard_claim() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = [
        "1m", "2m",
        "3m", "4m", "5m",
        "6m", "7m", "8m",
        "2p", "3p", "4p",
        "7s", "7s",
    ]
    game.hands[Seat.WEST] = [
        "1m", "2m",
        "3m", "4m", "5m",
        "6m", "7m", "8m",
        "2p", "3p", "4p",
        "7s", "8s",
    ]
    game.discards[Seat.EAST] = ["3m"]
    game.last_discard = (Seat.EAST, "3m")
    game.hint = (Seat.SOUTH, "draw")

    assert game.can_hu(Seat.SOUTH) is True
    assert game.can_hu(Seat.WEST) is False
    assert game.can_hu(Seat.EAST) is False

    assert game.hu(Seat.SOUTH) is True
    assert game.winner == Seat.SOUTH
    assert game.hint is None


def test_hu_requires_basic_winning_shape_for_self_draw() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = [
        "1m", "2m", "3m",
        "4m", "5m", "6m",
        "7m", "8m", "9m",
        "2p", "3p", "4p",
        "7s", "7s",
    ]
    game.hint = (Seat.SOUTH, "discard")

    assert game.can_hu(Seat.SOUTH) is True

    game.hands[Seat.SOUTH][-1] = "8s"
    assert game.can_hu(Seat.SOUTH) is False


def test_hu_counts_existing_melds_toward_required_sets() -> None:
    game = make_game()
    game.melds[Seat.SOUTH] = [Meld("pong", ("5m", "5m", "5m"), Seat.EAST)]
    game.hands[Seat.SOUTH] = [
        "1m", "2m", "3m",
        "4m", "5m", "6m",
        "7p", "8p", "9p",
        "2s", "2s",
    ]
    game.hint = (Seat.SOUTH, "discard")

    assert game.can_hu(Seat.SOUTH) is True


def test_player_view_auto_selects_drawn_tile_and_keeps_button_labels_stable() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = ["1m"] * 13
    view = PlayerView(game, Seat.SOUTH)

    game.hint = (Seat.SOUTH, "draw")
    initial_tree = view.render().items
    initial_actions = next(node for node in initial_tree if isinstance(node, dict) and node.get("$id") == "actions")
    assert [child["children"] for child in initial_actions["$children"]] == ["胡", "杠", "吃", "碰", "摸牌"]
    assert game.draw(Seat.SOUTH) == "9m"

    tree = view.render().items
    actions = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "actions")
    labels = [child["children"] for child in actions["$children"]]
    assert labels == ["胡", "杠", "吃", "碰", "出牌"]
    assert view.selected_index == len(game.hands[Seat.SOUTH]) - 1

    title = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "title")
    assert "牌墙" in title["$children"][1]["children"]


def test_player_view_renders_stable_discard_and_opponent_rows() -> None:
    game = make_game()
    game.hands[Seat.SOUTH] = ["1m"] * 13
    game.hands[Seat.EAST] = ["2m"] * 13
    game.hands[Seat.WEST] = ["3m"] * 13
    game.hands[Seat.NORTH] = ["4m"] * 13
    view = PlayerView(game, Seat.SOUTH)

    tree = view.render().items
    my_discards = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "my-discards")
    assert my_discards["children"] == "我的弃牌: -"

    right_block = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "other-west")
    assert right_block["style"]["borderBottom"] == "none"

    right_discard = right_block["$children"][1]
    assert right_discard["children"] == "弃: -"


def test_table_view_can_toggle_ai_and_ai_runs_simple_draw_discard_cycle() -> None:
    game = make_game()
    game.hands[Seat.EAST] = ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "1p", "2p", "3p", "4p"]
    table = TableView(game)

    table._on_toggle_ai(Seat.EAST)
    assert game.is_ai(Seat.EAST) is True

    seat_block = table._seat_block(Seat.EAST)
    toggle_button = seat_block["$children"][-1]
    assert toggle_button["children"] == "切回人工"

    assert game.run_ai_step() is True
    assert game.hint == (Seat.EAST, "discard")
    assert game.active_draw == (Seat.EAST, "9m")

    assert game.run_ai_step() is True
    assert game.hint == (Seat.SOUTH, "draw")
    assert len(game.discards[Seat.EAST]) == 1


def test_table_view_uses_responsive_seat_grid() -> None:
    game = make_game()
    table = TableView(game)
    tree = table.render().items

    seat_grid = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "seat-grid")
    assert seat_grid["style"]["flexWrap"] == "wrap"
    assert len(seat_grid["$children"]) == 4


def test_mahjong_app_contains_hidden_all_route() -> None:
    assert any(route.path == "/all" for route in app.routes)


def test_all_view_renders_table_and_four_player_views() -> None:
    async def _test() -> None:
        channel = MockChannel()
        vp = ViewPort(all_view, channel)
        await vp.initialize()
        await all_view.rendered()

        paths = [f.get("viewId") for m in channel.messages
                 for f in m.get("frames", [])]
        assert [] in paths
        assert ["table"] in paths
        assert ["all-east"] in paths
        assert ["all-south"] in paths
        assert ["all-west"] in paths
        assert ["all-north"] in paths

    asyncio.run(_test())
