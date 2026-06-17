"""多视图麻将 demo — 提示型流程 + 吃碰杠胡 + AI 托管 + all 调试入口。"""

from __future__ import annotations

import asyncio
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mutgui import Callback, View, ViewBlock

from demo.framework import DemoApp, MutguiRoute


# ---------------------------------------------------------------------------
# 麻将牌定义与 Unicode 映射
# ---------------------------------------------------------------------------


class Seat(Enum):
    EAST = "east"
    SOUTH = "south"
    WEST = "west"
    NORTH = "north"


SEAT_NAMES = {
    Seat.EAST: "东",
    Seat.SOUTH: "南",
    Seat.WEST: "西",
    Seat.NORTH: "北",
}

SEAT_ORDER = [Seat.EAST, Seat.SOUTH, Seat.WEST, Seat.NORTH]
NEXT_SEAT = {
    Seat.EAST: Seat.SOUTH,
    Seat.SOUTH: Seat.WEST,
    Seat.WEST: Seat.NORTH,
    Seat.NORTH: Seat.EAST,
}

TILES: list[str] = []
for _suit in ("m", "p", "s"):
    for _num in range(1, 10):
        TILES.append(f"{_num}{_suit}")
TILES.extend(["east_w", "south_w", "west_w", "north_w"])
TILES.extend(["zhong", "fa", "bai"])

TILE_UNICODE: dict[str, str] = {}
for _i in range(9):
    TILE_UNICODE[f"{_i + 1}m"] = chr(0x1F007 + _i)
for _i in range(9):
    TILE_UNICODE[f"{_i + 1}p"] = chr(0x1F019 + _i)
for _i in range(9):
    TILE_UNICODE[f"{_i + 1}s"] = chr(0x1F010 + _i)
TILE_UNICODE["east_w"] = chr(0x1F000)
TILE_UNICODE["south_w"] = chr(0x1F001)
TILE_UNICODE["west_w"] = chr(0x1F002)
TILE_UNICODE["north_w"] = chr(0x1F003)
TILE_UNICODE["zhong"] = chr(0x1F004)
TILE_UNICODE["fa"] = chr(0x1F005)
TILE_UNICODE["bai"] = chr(0x1F006)

TILE_BACK = chr(0x1F02B)
TILE_SORT_KEY = {tile: index for index, tile in enumerate(TILES)}
MAHJONG_TILE_FONT = '"Segoe UI Symbol", "SimSun-ExtB", "MingLiU-ExtB", "SimSun", serif'
TABLE_TILE_SIZE = "clamp(16px, 2.2vw, 22px)"
TABLE_MELD_SIZE = "clamp(11px, 1.5vw, 14px)"
DISCARD_TILE_SIZE = "clamp(13px, 1.8vw, 18px)"
HAND_TILE_SIZE = "clamp(36px, 8vw, 72px)"
HAND_MELD_SIZE = "clamp(29px, 6.4vw, 58px)"
OPPONENT_ROWS = [(2, "对面"), (3, "左家"), (1, "右家")]
AI_ACTION_DELAY_SECONDS = 5.0

JsonBlock = dict[str, Any]
AiPayload = str | tuple[str, str] | None
AiPlan = tuple[Seat, str, AiPayload]


def tile_char(tile: str) -> str:
    return TILE_UNICODE.get(tile, "?")


def sort_hand(hand: list[str]) -> list[str]:
    return sorted(hand, key=lambda tile: TILE_SORT_KEY.get(tile, 999))


def is_number_tile(tile: str) -> bool:
    return len(tile) == 2 and tile[0].isdigit() and tile[1] in {"m", "p", "s"}


def tile_number(tile: str) -> int:
    return int(tile[0])


def tile_suit(tile: str) -> str:
    return tile[1]


def chi_sequence(tiles: list[str]) -> list[str] | None:
    if len(tiles) != 3 or any(not is_number_tile(tile) for tile in tiles):
        return None
    suits = {tile[1] for tile in tiles}
    if len(suits) != 1:
        return None
    nums = sorted(int(tile[0]) for tile in tiles)
    if nums[0] + 1 != nums[1] or nums[1] + 1 != nums[2]:
        return None
    return sort_hand(list(tiles))


def format_tiles(tiles: list[str] | tuple[str, ...], *, spaced: bool = True) -> str:
    chars = [tile_char(tile) for tile in tiles]
    return " ".join(chars) if spaced else "".join(chars)


def hint_action_text(action: str) -> str:
    return "摸牌" if action == "draw" else "出牌"


def tile_font_style(font_size: int | str, **extra: Any) -> dict[str, Any]:
    return {"fontSize": font_size, "fontFamily": MAHJONG_TILE_FONT, **extra}


@dataclass(frozen=True)
class Meld:
    type: str
    tiles: tuple[str, ...]
    source_seat: Seat | None
    concealed: bool = False


# ---------------------------------------------------------------------------
# 牌局数据模型
# ---------------------------------------------------------------------------


class MahjongGame:
    def __init__(self) -> None:
        super().__init__()
        self.wall: list[str] = []
        self.hands: dict[Seat, list[str]] = {seat: [] for seat in Seat}
        self.discards: dict[Seat, list[str]] = {seat: [] for seat in Seat}
        self.melds: dict[Seat, list[Meld]] = {seat: [] for seat in Seat}
        self.last_discard: tuple[Seat, str] | None = None
        self.hint: tuple[Seat, str] | None = None
        self.active_draw: tuple[Seat, str] | None = None
        self.winner: Seat | None = None
        self.ai_seats: set[Seat] = set()
        self._on_change: list[Callable[[], None]] = []
        self._ai_task: asyncio.Task[None] | None = None
        self.ai = MahjongAi(self)

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change.append(callback)

    def _notify(self) -> None:
        for callback in self._on_change:
            callback()
        self._schedule_ai_action()

    def is_started(self) -> bool:
        return self.hint is not None or self.winner is not None

    def is_ai(self, seat: Seat) -> bool:
        return seat in self.ai_seats

    def toggle_ai(self, seat: Seat) -> None:
        if seat in self.ai_seats:
            self.ai_seats.remove(seat)
        else:
            self.ai_seats.add(seat)
        self._notify()

    def status_text(self) -> str:
        if self.winner is not None:
            return f"{SEAT_NAMES[self.winner]}家胡牌"
        if self.last_discard is not None:
            source, tile = self.last_discard
            return f"等待响应：{SEAT_NAMES[source]}家打出 {tile_char(tile)}"
        if self.hint is not None:
            seat, action = self.hint
            return f"提示：{SEAT_NAMES[seat]}家{hint_action_text(action)}"
        return "未开局"

    def active_draw_tile(self, seat: Seat) -> str | None:
        if self.active_draw is None or self.active_draw[0] != seat:
            return None
        return self.active_draw[1]

    def deal(self) -> None:
        deck = TILES * 4
        random.shuffle(deck)
        for seat in Seat:
            self.hands[seat] = sort_hand(deck[:13])
            self.discards[seat] = []
            self.melds[seat] = []
            deck = deck[13:]
        self.wall = deck
        self.last_discard = None
        self.hint = (Seat.EAST, "draw")
        self.active_draw = None
        self.winner = None
        self._notify()

    def run_ai_step(self) -> bool:
        plan = self.ai.plan_action()
        if plan is None:
            return False
        seat, action, payload = plan
        if action == "hu":
            return self.hu(seat)
        if action == "draw":
            return self.draw(seat) is not None
        if action == "discard":
            return payload is not None and self.discard(seat, payload)
        if action == "pong":
            return self.pong(seat)
        if action == "chi":
            return isinstance(payload, tuple) and self.chi(seat, payload[0], payload[1])
        if action == "kong":
            return self.kong(seat, payload)
        return False

    def can_draw(self, seat: Seat) -> bool:
        return (
            self.winner is None
            and self.hint == (seat, "draw")
            and bool(self.wall)
        )

    def can_discard(self, seat: Seat, tile: str | None = None) -> bool:
        if self.winner is not None or self.hint != (seat, "discard") or not self.hands[seat]:
            return False
        if tile is None:
            return True
        return tile in self.hands[seat]

    def can_pong(self, seat: Seat) -> bool:
        if self.winner is not None or self.last_discard is None:
            return False
        source, tile = self.last_discard
        return source != seat and self.hands[seat].count(tile) >= 2

    def can_chi(self, seat: Seat, tiles: list[str]) -> bool:
        if self.winner is not None or self.last_discard is None:
            return False
        source, tile = self.last_discard
        if source == seat or NEXT_SEAT[source] != seat or len(tiles) != 2:
            return False
        if not self._has_tiles(self.hands[seat], tiles):
            return False
        return chi_sequence([tile, *tiles]) is not None

    def chi_options(self, seat: Seat) -> list[tuple[str, str]]:
        if self.winner is not None or self.last_discard is None:
            return []
        source, tile = self.last_discard
        if source == seat or NEXT_SEAT[source] != seat or not is_number_tile(tile):
            return []

        tile_num = tile_number(tile)
        suit = tile_suit(tile)
        options: list[tuple[str, str]] = []
        hand_counts = Counter(self.hands[seat])
        for start in range(max(1, tile_num - 2), min(7, tile_num) + 1):
            sequence = [f"{start + offset}{suit}" for offset in range(3)]
            if tile not in sequence:
                continue
            needed = [seq_tile for seq_tile in sequence if seq_tile != tile]
            if self._has_tiles(self.hands[seat], needed):
                option = tuple(sort_hand(needed))
                if option not in options:
                    options.append(option)
        return options

    def can_exposed_kong(self, seat: Seat) -> bool:
        if self.winner is not None or self.last_discard is None:
            return False
        source, tile = self.last_discard
        return source != seat and self.hands[seat].count(tile) >= 3

    def can_concealed_kong(self, seat: Seat, tile: str | None) -> bool:
        if self.winner is not None or self.hint != (seat, "discard") or tile is None:
            return False
        return self.hands[seat].count(tile) >= 4

    def can_kong(self, seat: Seat, tile: str | None) -> bool:
        return self.can_exposed_kong(seat) or self.can_concealed_kong(seat, tile)

    def can_hu(self, seat: Seat) -> bool:
        if self.winner is not None or not self.is_started():
            return False
        if self.last_discard is not None:
            source, tile = self.last_discard
            if source == seat:
                return False
            return self._is_winning_hand(seat, self.hands[seat] + [tile])
        if self.hint != (seat, "discard"):
            return False
        return self._is_winning_hand(seat, list(self.hands[seat]))

    def draw(self, seat: Seat) -> str | None:
        if not self.can_draw(seat):
            return None
        tile = self.wall.pop(0)
        self.hands[seat].append(tile)
        self.last_discard = None
        self.active_draw = (seat, tile)
        self.hint = (seat, "discard")
        self._notify()
        return tile

    def discard(self, seat: Seat, tile: str) -> bool:
        if not self.can_discard(seat, tile):
            return False
        self.hands[seat].remove(tile)
        self.hands[seat] = sort_hand(self.hands[seat])
        self.discards[seat].append(tile)
        self.last_discard = (seat, tile)
        self.active_draw = None
        self.hint = (NEXT_SEAT[seat], "draw")
        self._notify()
        return True

    def pong(self, seat: Seat) -> bool:
        if not self.can_pong(seat):
            return False
        source, tile = self._claim_last_discard()
        self._remove_tiles(seat, [tile, tile])
        self.hands[seat] = sort_hand(self.hands[seat])
        self.melds[seat].append(Meld("pong", (tile, tile, tile), source))
        self.active_draw = None
        self.hint = (seat, "discard")
        self._notify()
        return True

    def chi(self, seat: Seat, tile1: str, tile2: str) -> bool:
        chosen = [tile1, tile2]
        if not self.can_chi(seat, chosen):
            return False
        source, tile = self._claim_last_discard()
        self._remove_tiles(seat, chosen)
        self.hands[seat] = sort_hand(self.hands[seat])
        sequence = chi_sequence([tile, tile1, tile2])
        if sequence is None:
            return False
        self.melds[seat].append(Meld("chi", tuple(sequence), source))
        self.active_draw = None
        self.hint = (seat, "discard")
        self._notify()
        return True

    def kong(self, seat: Seat, tile: str | None) -> bool:
        if self.can_exposed_kong(seat):
            source, tile = self._claim_last_discard()
            self._remove_tiles(seat, [tile, tile, tile])
            self.hands[seat] = sort_hand(self.hands[seat])
            self.melds[seat].append(Meld("kong", (tile, tile, tile, tile), source))
            self._draw_after_kong(seat)
            return True
        if self.can_concealed_kong(seat, tile):
            if tile is None:
                return False
            self._remove_tiles(seat, [tile, tile, tile, tile])
            self.hands[seat] = sort_hand(self.hands[seat])
            self.melds[seat].append(Meld("kong", (tile, tile, tile, tile), None, concealed=True))
            self._draw_after_kong(seat)
            return True
        return False

    def hu(self, seat: Seat) -> bool:
        if not self.can_hu(seat):
            return False
        self.winner = seat
        self.hint = None
        self.active_draw = None
        self._notify()
        return True

    def _draw_after_kong(self, seat: Seat) -> None:
        if not self.wall:
            self.active_draw = None
            self.hint = (seat, "discard")
            self._notify()
            return
        tile = self.wall.pop(0)
        self.hands[seat].append(tile)
        self.active_draw = (seat, tile)
        self.hint = (seat, "discard")
        self._notify()

    def _claim_last_discard(self) -> tuple[Seat, str]:
        if self.last_discard is None:
            raise RuntimeError("last_discard 不存在，无法 claim")
        source, tile = self.last_discard
        if self.discards[source] and self.discards[source][-1] == tile:
            self.discards[source].pop()
        self.last_discard = None
        return source, tile

    def _remove_tiles(self, seat: Seat, tiles: list[str]) -> None:
        if not self._has_tiles(self.hands[seat], tiles):
            raise RuntimeError("手牌不足，无法移除指定牌")
        for tile in tiles:
            self.hands[seat].remove(tile)

    def _has_tiles(self, hand: list[str], tiles: list[str]) -> bool:
        hand_counts: Counter[str] = Counter(hand)
        for tile, count in Counter(tiles).items():
            if hand_counts[tile] < count:
                return False
        return True

    def _is_winning_hand(self, seat: Seat, tiles: list[str]) -> bool:
        required_melds = 4 - len(self.melds[seat])
        if required_melds < 0 or len(tiles) != required_melds * 3 + 2:
            return False

        counts: Counter[str] = Counter(tiles)
        for tile, count in list(counts.items()):
            if count < 2:
                continue
            counts[tile] -= 2
            if counts[tile] == 0:
                del counts[tile]
            if self._can_form_melds(counts, required_melds):
                return True
            counts[tile] = count
        return False

    def _schedule_ai_action(self) -> None:
        if self.ai.plan_action() is None:
            if self._ai_task is not None and not self._ai_task.done():
                self._ai_task.cancel()
            self._ai_task = None
            return

        if self._ai_task is not None and not self._ai_task.done():
            self._ai_task.cancel()

        try:
            loop = asyncio.get_running_loop()
            self._ai_task = loop.create_task(self._run_ai_action())
        except RuntimeError:
            self._ai_task = None

    async def _run_ai_action(self) -> None:
        try:
            await asyncio.sleep(AI_ACTION_DELAY_SECONDS)
        except asyncio.CancelledError:
            return

        self._ai_task = None
        self.run_ai_step()

    def _can_form_melds(self, counts: Counter[str], required_melds: int) -> bool:
        if required_melds == 0:
            return not counts

        remaining_tiles = [tile for tile, count in counts.items() if count > 0]
        if not remaining_tiles:
            return False

        tile = min(remaining_tiles, key=lambda item: TILE_SORT_KEY.get(item, 999))
        current = counts[tile]

        if current >= 3:
            next_counts = counts.copy()
            next_counts[tile] -= 3
            if next_counts[tile] == 0:
                del next_counts[tile]
            if self._can_form_melds(next_counts, required_melds - 1):
                return True

        if is_number_tile(tile) and tile_number(tile) <= 7:
            second = f"{tile_number(tile) + 1}{tile_suit(tile)}"
            third = f"{tile_number(tile) + 2}{tile_suit(tile)}"
            if counts.get(second, 0) > 0 and counts.get(third, 0) > 0:
                next_counts = counts.copy()
                next_counts[tile] -= 1
                next_counts[second] -= 1
                next_counts[third] -= 1
                for seq_tile in (tile, second, third):
                    if next_counts[seq_tile] == 0:
                        del next_counts[seq_tile]
                if self._can_form_melds(next_counts, required_melds - 1):
                    return True

        return False


# ---------------------------------------------------------------------------
# AI 与 UI 辅助
# ---------------------------------------------------------------------------


class MahjongAi:
    def __init__(self, game: MahjongGame) -> None:
        self.game = game

    def plan_action(self) -> AiPlan | None:
        game = self.game
        if game.winner is not None or not game.ai_seats:
            return None

        discard_claim = self._plan_discard_claim()
        if discard_claim is not None:
            return discard_claim

        if game.hint is None:
            return None
        seat, action = game.hint
        if seat not in game.ai_seats:
            return None
        if game.can_hu(seat):
            return (seat, "hu", None)
        if action == "draw" and game.can_draw(seat):
            return (seat, "draw", None)
        if action != "discard":
            return None
        kong_tile = self._choose_concealed_kong_tile(seat)
        if kong_tile is not None:
            return (seat, "kong", kong_tile)
        discard_tile = self._choose_discard(seat)
        if discard_tile is not None:
            return (seat, "discard", discard_tile)
        return None

    def _plan_discard_claim(self) -> AiPlan | None:
        game = self.game
        if game.last_discard is None:
            return None
        source, _tile = game.last_discard
        claim_order = [NEXT_SEAT[source], NEXT_SEAT[NEXT_SEAT[source]], NEXT_SEAT[NEXT_SEAT[NEXT_SEAT[source]]]]
        for seat in claim_order:
            if seat in game.ai_seats and game.can_hu(seat):
                return (seat, "hu", None)
        for seat in claim_order:
            if seat in game.ai_seats and game.can_exposed_kong(seat):
                return (seat, "kong", None)
        for seat in claim_order:
            if seat in game.ai_seats and self._should_pong(seat):
                return (seat, "pong", None)
        next_seat = NEXT_SEAT[source]
        if next_seat in game.ai_seats:
            option = self._choose_chi_option(next_seat)
            if option is not None:
                return (next_seat, "chi", option)
        return None

    def _choose_discard(self, seat: Seat) -> str | None:
        hand = self.game.hands[seat]
        if not hand:
            return None
        return min(
            hand,
            key=lambda tile: (
                self._tile_value(hand, tile),
                0 if not is_number_tile(tile) else 1,
                -tile_number(tile) if is_number_tile(tile) else 0,
                -TILE_SORT_KEY.get(tile, 999),
            ),
        )

    def _tile_value(self, hand: list[str], tile: str) -> float:
        counts = Counter(hand)
        value = float(counts[tile] * 2)
        if not is_number_tile(tile):
            return value

        num = tile_number(tile)
        suit = tile_suit(tile)
        value += counts.get(f"{num - 1}{suit}", 0) * 1.2
        value += counts.get(f"{num + 1}{suit}", 0) * 1.2
        value += counts.get(f"{num - 2}{suit}", 0) * 0.6
        value += counts.get(f"{num + 2}{suit}", 0) * 0.6
        if num in (1, 9):
            value -= 0.5
        if num in (2, 8):
            value -= 0.2
        return value

    def _should_pong(self, seat: Seat) -> bool:
        game = self.game
        if not game.can_pong(seat) or game.last_discard is None:
            return False
        _source, tile = game.last_discard
        if not is_number_tile(tile):
            return True
        return self._tile_value(game.hands[seat], tile) >= 5.0

    def _choose_chi_option(self, seat: Seat) -> tuple[str, str] | None:
        options = self.game.chi_options(seat)
        if not options:
            return None
        return min(
            options,
            key=lambda option: (
                self._tile_value(self.game.hands[seat], option[0]) + self._tile_value(self.game.hands[seat], option[1]),
                TILE_SORT_KEY.get(option[0], 999),
                TILE_SORT_KEY.get(option[1], 999),
            ),
        )

    def _choose_concealed_kong_tile(self, seat: Seat) -> str | None:
        game = self.game
        for tile in sort_hand(list(dict.fromkeys(game.hands[seat]))):
            if game.can_concealed_kong(seat, tile):
                return tile
        return None


def meld_text(meld: Meld) -> str:
    if meld.concealed:
        return TILE_BACK * 4
    source = ""
    if meld.type in {"pong", "kong"} and meld.source_seat is not None:
        source = f"←{SEAT_NAMES[meld.source_seat]}"
    return f"{format_tiles(meld.tiles, spaced=False)}{source}"


def claim_hint(game: MahjongGame, seat: Seat) -> str:
    if game.winner is not None:
        text = "牌局结束"
    elif game.can_hu(seat):
        text = "可胡牌"
    elif game.last_discard is not None:
        actions: list[str] = []
        if game.can_pong(seat):
            actions.append("碰")
        chi_count = len(game.chi_options(seat))
        if chi_count == 1:
            actions.append("吃")
        elif chi_count > 1:
            actions.append(f"吃({chi_count}种)")
        if game.can_exposed_kong(seat):
            actions.append("明杠")
        text = f"可操作：{' / '.join(actions)}" if actions else "等待中"
    elif game.hint == (seat, "draw"):
        text = "轮到你摸牌"
    elif game.hint == (seat, "discard"):
        text = "轮到你出牌"
    else:
        text = "等待中"
    return f"{text} · 牌墙 {len(game.wall)}"


def seat_is_active(game: MahjongGame, seat: Seat) -> bool:
    return game.hint is not None and game.hint[0] == seat


def meld_summary(melds: list[Meld]) -> str:
    return " ".join(meld_text(meld) for meld in melds) if melds else "-"


def discard_summary(tiles: list[str]) -> str:
    return format_tiles(tiles) if tiles else "-"


def action_button(
    button_id: str,
    label: str,
    on_click: Callback,
    *,
    disabled: bool = False,
    danger: bool = False,
    button_type: str | None = None,
    size: str | None = None,
    style: dict[str, Any] | None = None,
) -> JsonBlock:
    button: JsonBlock = {
        "$component": "antd.Button",
        "$id": button_id,
        "children": label,
        "disabled": disabled,
        "onClick": on_click,
    }
    if danger:
        button["danger"] = True
    if button_type is not None:
        button["type"] = button_type
    if size is not None:
        button["size"] = size
    if style is not None:
        button["style"] = style
    return button


# ---------------------------------------------------------------------------
# TableView — 牌桌视图
# ---------------------------------------------------------------------------


class TableView(View):
    id = "table"
    game: MahjongGame
    link_base: str
    show_links: bool

    def __init__(
        self,
        game: MahjongGame,
        *,
        link_base: str = "",
        show_links: bool = True,
    ) -> None:
        super().__init__()
        self.game = game
        self.link_base = link_base
        self.show_links = show_links
        game.on_change(self.invalidate)

    def render(self) -> ViewBlock:
        game = self.game
        items: list[dict[str, Any]] = [{
            "$component": "html.div",
            "$id": "title",
            "style": {"textAlign": "center", "marginBottom": 16},
            "$children": [{
                "$component": "html.span",
                "$id": "t1",
                "style": {"fontSize": 20, "fontWeight": "bold"},
                "children": "🀄 麻将牌桌",
            }],
        }]

        items.append({
            "$component": "html.div",
            "$id": "status",
            "style": {
                "textAlign": "center",
                "marginBottom": 8,
                "color": "#69b1ff" if game.last_discard else "var(--mutgui-text-dim)",
                "fontSize": 14,
            },
            "children": game.status_text(),
        })

        items.append({
            "$component": "html.div",
            "$id": "center-info",
            "style": {
                "textAlign": "center",
                "padding": "14px 12px",
                "border": "1px dashed var(--mutgui-border)",
                "borderRadius": 8,
                "marginBottom": 16,
            },
            "$children": [{
                "$component": "html.div",
                "$id": "center-status",
                "style": {"fontSize": 16, "marginBottom": 6},
                "children": game.status_text(),
            }, {
                "$component": "html.div",
                "$id": "center-last",
                "style": {"fontSize": 14, "color": "var(--mutgui-text-dim)"},
                "children": f"{self._last_discard_text()} · 牌墙剩余：{len(game.wall)}",
            }],
        })

        items.append({
            "$component": "html.div",
            "$id": "seat-grid",
            "style": {
                "display": "flex",
                "flexWrap": "wrap",
                "gap": 12,
                "justifyContent": "center",
                "alignItems": "stretch",
            },
            "$children": [self._seat_block(seat) for seat in SEAT_ORDER],
        })

        items.append({
            "$component": "html.div",
            "$id": "actions",
            "style": {"textAlign": "center", "marginTop": 24},
            "$children": [{
                "$component": "antd.Button",
                "$id": "deal",
                "type": "primary",
                "children": "重新发牌" if game.is_started() else "发牌",
                "onClick": Callback(self._on_deal),
            }],
        })
        return ViewBlock(items)

    def _seat_block(self, seat: Seat) -> dict[str, Any]:
        game = self.game
        name = SEAT_NAMES[seat]
        is_hint_target = seat_is_active(game, seat)
        is_ai = game.is_ai(seat)
        if is_hint_target:
            name = f"▶ {name}"
        if is_ai:
            name = f"{name} · AI"

        children: list[dict[str, Any] | View] = [{
            "$component": "html.div",
            "$id": f"label-{seat.value}",
            "style": {
                "fontSize": 15,
                "fontWeight": "bold",
                "color": "#ff7875" if is_hint_target else "#69b1ff",
            },
            "children": name,
        }]
        if game.hands[seat]:
            children.append({
                "$component": "html.div",
                "$id": f"hand-{seat.value}",
                "style": tile_font_style(TABLE_TILE_SIZE, letterSpacing=2, margin="4px 0"),
                "children": TILE_BACK * len(game.hands[seat]),
            })
        if game.melds[seat]:
            children.append({
                "$component": "html.div",
                "$id": f"melds-{seat.value}",
                "style": tile_font_style(TABLE_MELD_SIZE, margin="4px 0"),
                "children": f"亮: {meld_summary(game.melds[seat])}",
            })
        if game.discards[seat]:
            children.append({
                "$component": "html.div",
                "$id": f"disc-{seat.value}",
                "style": tile_font_style(DISCARD_TILE_SIZE, color="var(--mutgui-text-dim)", margin="4px 0"),
                "children": f"弃: {discard_summary(game.discards[seat])}",
            })
        if self.show_links:
            children.append({
                "$component": "html.a",
                "$id": f"enter-{seat.value}",
                "href": f"{self.link_base}{seat.value}/",
                "style": {
                    "fontSize": 12,
                    "color": "#69b1ff",
                    "display": "block",
                    "marginTop": 4,
                },
                    "children": f"进入{SEAT_NAMES[seat]}家",
             })
        children.append(action_button(
            f"ai-{seat.value}",
            "切回人工" if is_ai else "切到AI",
            Callback(self._on_toggle_ai, seat),
            size="small",
            style={"marginTop": 6},
        ))
        return {
            "$component": "html.div",
            "$id": f"seat-{seat.value}",
            "style": {
                "flex": "1 1 240px",
                "maxWidth": 360,
                "minWidth": 220,
                "padding": "12px 14px",
                "border": "1px solid var(--mutgui-border)",
                "borderRadius": 8,
                "textAlign": "center",
            },
            "$children": children,
        }

    def _last_discard_text(self) -> str:
        if self.game.last_discard is None:
            return "最后弃牌：无"
        source, tile = self.game.last_discard
        return f"最后弃牌：{SEAT_NAMES[source]}家 {tile_char(tile)}"

    def _on_deal(self) -> None:
        self.game.deal()

    def _on_toggle_ai(self, seat: Seat) -> None:
        self.game.toggle_ai(seat)


# ---------------------------------------------------------------------------
# PlayerView — 玩家视图
# ---------------------------------------------------------------------------


class PlayerView(View):
    game: MahjongGame
    seat: Seat
    show_back_button: bool
    selected_index: int | None

    def __init__(
        self,
        game: MahjongGame,
        seat: Seat,
        *,
        view_id_prefix: str = "player",
        show_back_button: bool = True,
    ) -> None:
        super().__init__()
        self.id = f"{view_id_prefix}-{seat.value}"
        self.game = game
        self.seat = seat
        self.show_back_button = show_back_button
        self.selected_index: int | None = None
        game.on_change(self._on_game_change)

    def render(self) -> ViewBlock:
        game = self.game
        self._normalize_selection()
        selected_tile = self._selected_tile()
        chi_options = game.chi_options(self.seat)
        is_ai = game.is_ai(self.seat)
        primary_label = "摸牌" if game.can_draw(self.seat) else "出牌"
        primary_enabled = game.can_draw(self.seat) or (
            selected_tile is not None and game.can_discard(self.seat, selected_tile)
        )

        items: list[dict[str, Any] | View] = [
            self._title_block(),
            self._status_line_block(),
            *self._opponent_blocks(),
            {"$component": "antd.Divider", "$id": "div1", "style": {"margin": "12px 0"}},
            self._my_discard_block(),
            {
                "$component": "html.div",
                "$id": "hand-label",
                "style": {"fontSize": 14, "color": "var(--mutgui-text-dim)", "marginBottom": 4},
                "children": "我的牌：",
            },
            self._hand_block(),
            self._actions_block(is_ai, selected_tile, chi_options, primary_label, primary_enabled),
            self._chi_options_block(chi_options, is_ai),
        ]

        if is_ai:
            items.append({
                "$component": "html.div",
                "$id": "ai-status",
                "style": {"fontSize": 13, "color": "var(--mutgui-text-dim)", "marginTop": 4},
                "children": "当前为 AI 托管，牌桌可切回人工。",
            })

        if self.show_back_button:
            items.append({
                "$component": "html.div",
                "$id": "back-wrap",
                "style": {"marginTop": 8},
                "$children": [{
                    "$component": "antd.Button",
                    "$id": "back",
                    "children": "返回牌桌",
                    "onClick": Callback(self._go_table),
                }],
             })
        return ViewBlock(items)

    def _title_block(self) -> JsonBlock:
        return {
            "$component": "html.div",
            "$id": "title",
            "style": {"textAlign": "center", "marginBottom": 12},
            "$children": [{
                "$component": "html.span",
                "$id": "t1",
                "style": {"fontSize": 18, "fontWeight": "bold"},
                "children": f"{SEAT_NAMES[self.seat]}家",
            }, {
                "$component": "html.span",
                "$id": "hint",
                "style": {
                    "fontSize": 14,
                    "marginLeft": 12,
                    "color": "#ff7875" if seat_is_active(self.game, self.seat) else "var(--mutgui-text-dim)",
                },
                "children": claim_hint(self.game, self.seat),
            }],
        }

    def _status_line_block(self) -> JsonBlock:
        return {
            "$component": "html.div",
            "$id": "status-line",
            "style": {
                "fontSize": 13,
                "color": "var(--mutgui-text-dim)",
                "marginBottom": 10,
                "textAlign": "center",
            },
            "children": self.game.status_text(),
        }

    def _opponent_blocks(self) -> list[JsonBlock]:
        my_index = SEAT_ORDER.index(self.seat)
        return [
            self._other_seat_block(
                SEAT_ORDER[(my_index + offset) % 4],
                relation,
                is_last=row_index == len(OPPONENT_ROWS) - 1,
            )
            for row_index, (offset, relation) in enumerate(OPPONENT_ROWS)
        ]

    def _my_discard_block(self) -> JsonBlock:
        return {
            "$component": "html.div",
            "$id": "my-discards",
            "style": tile_font_style(DISCARD_TILE_SIZE, marginBottom=8),
            "children": f"我的弃牌: {discard_summary(self.game.discards[self.seat])}",
        }

    def _hand_block(self) -> JsonBlock:
        return {
            "$component": "html.div",
            "$id": "my-hand",
            "style": {
                "display": "flex",
                "flexWrap": "wrap",
                "alignItems": "flex-end",
                "columnGap": 2,
                "rowGap": 6,
                "lineHeight": 1.1,
                "minHeight": 72,
                "maxWidth": "100%",
            },
            "$children": self._meld_spans() + self._hand_tile_spans(),
        }

    def _meld_spans(self) -> list[JsonBlock]:
        return [{
            "$component": "html.span",
            "$id": f"my-meld-{index}",
            "style": tile_font_style(
                HAND_MELD_SIZE,
                display="inline-flex",
                alignItems="flex-end",
                marginRight=12,
                marginBottom=4,
            ),
            "children": meld_text(meld),
        } for index, meld in enumerate(self.game.melds[self.seat])]

    def _hand_tile_spans(self) -> list[JsonBlock]:
        active_draw = self.game.active_draw_tile(self.seat)
        tiles: list[JsonBlock] = []
        for index, tile in enumerate(self.game.hands[self.seat]):
            tiles.append({
                "$component": "html.span",
                "$id": f"tile-{index}",
                "style": self._hand_tile_style(index, tile, active_draw),
                "children": tile_char(tile),
                "onClick": Callback(self._on_toggle_tile, index),
            })
        return tiles

    def _hand_tile_style(self, index: int, tile: str, active_draw: str | None) -> dict[str, Any]:
        is_selected = index == self.selected_index
        is_drawn = active_draw is not None and index == len(self.game.hands[self.seat]) - 1 and tile == active_draw
        style: dict[str, Any] = tile_font_style(
            HAND_TILE_SIZE,
            cursor="pointer",
            display="inline-flex",
            alignItems="flex-end",
            padding="2px 1px",
            borderRadius=4,
            transition="all 0.15s",
            marginTop=-10 if is_selected else 0,
            marginBottom=4,
            marginRight=2,
            background="oklch(0.32 0.05 70)" if is_selected else "transparent",
        )
        if is_drawn:
            style["marginLeft"] = 12
        return style

    def _actions_block(
        self,
        is_ai: bool,
        selected_tile: str | None,
        chi_options: list[tuple[str, str]],
        primary_label: str,
        primary_enabled: bool,
    ) -> JsonBlock:
        return {
            "$component": "html.div",
            "$id": "actions",
            "style": {"marginTop": 16, "display": "flex", "gap": 8, "flexWrap": "wrap"},
            "$children": [
                action_button("hu", "胡", Callback(self._on_hu), disabled=is_ai or not self.game.can_hu(self.seat), danger=True),
                action_button("kong", "杠", Callback(self._on_kong), disabled=is_ai or not self.game.can_kong(self.seat, selected_tile)),
                action_button("chi", "吃", Callback(self._on_chi), disabled=is_ai or len(chi_options) != 1),
                action_button("pong", "碰", Callback(self._on_pong), disabled=is_ai or not self.game.can_pong(self.seat)),
                action_button(
                    "primary",
                    primary_label,
                    Callback(self._on_primary_action),
                    disabled=is_ai or not primary_enabled,
                    button_type="primary",
                ),
            ],
        }

    def _chi_options_block(self, chi_options: list[tuple[str, str]], is_ai: bool) -> JsonBlock:
        option_buttons = [
            action_button(
                f"chi-option-{index}",
                f"吃 {format_tiles(option)}",
                Callback(self._on_chi_option, list(option)),
                disabled=is_ai,
            )
            for index, option in enumerate(chi_options)
        ] if len(chi_options) > 1 else []
        return {
            "$component": "html.div",
            "$id": "chi-options",
            "style": {"minHeight": 40, "marginTop": 8},
            "$children": [{
                "$component": "html.div",
                "$id": "chi-options-inner",
                "style": {"display": "flex", "gap": 8, "flexWrap": "wrap"},
                "$children": option_buttons,
            }],
        }

    def _other_seat_block(self, seat: Seat, relation: str, *, is_last: bool = False) -> dict[str, Any]:
        game = self.game
        children: list[dict[str, Any]] = [{
            "$component": "html.span",
            "$id": f"oname-{seat.value}",
            "style": {
                "fontWeight": "bold",
                "color": "#ff7875" if seat_is_active(game, seat) else "var(--mutgui-text)",
            },
            "children": f"{relation}（{SEAT_NAMES[seat]}）",
        }, {
            "$component": "html.span",
            "$id": f"ohand-{seat.value}",
            "style": tile_font_style(TABLE_TILE_SIZE, marginLeft=8),
            "children": TILE_BACK * len(game.hands[seat]),
        }, {
            "$component": "html.span",
            "$id": f"omeld-{seat.value}",
            "style": tile_font_style(TABLE_MELD_SIZE, marginLeft=10),
            "children": f"亮: {meld_summary(game.melds[seat])}",
        }]
        return {
            "$component": "html.div",
            "$id": f"other-{seat.value}",
            "style": {"padding": "6px 0", "borderBottom": "none" if is_last else "1px solid var(--mutgui-border)"},
            "$children": [
                {
                    "$component": "html.div",
                    "$id": f"other-top-{seat.value}",
                    "$children": children,
                },
                {
                    "$component": "html.div",
                    "$id": f"odisc-{seat.value}",
                    "style": tile_font_style(DISCARD_TILE_SIZE, color="var(--mutgui-text-dim)", marginTop=2),
                    "children": f"弃: {discard_summary(game.discards[seat])}",
                },
            ],
        }

    def _normalize_selection(self) -> None:
        hand_len = len(self.game.hands[self.seat])
        if self.selected_index is not None and not (0 <= self.selected_index < hand_len):
            self.selected_index = None

    def _selected_tile(self) -> str | None:
        self._normalize_selection()
        if self.selected_index is None:
            return None
        return self.game.hands[self.seat][self.selected_index]

    def _clear_selection(self) -> None:
        self.selected_index = None

    def _on_toggle_tile(self, index: int) -> None:
        if self.game.is_ai(self.seat):
            return
        if self.selected_index == index:
            self.selected_index = None
        else:
            self.selected_index = index
        self.invalidate()

    def _on_game_change(self) -> None:
        active_draw = self.game.active_draw_tile(self.seat)
        if active_draw is not None and self.game.hint == (self.seat, "discard") and self.game.hands[self.seat]:
            self.selected_index = len(self.game.hands[self.seat]) - 1
        else:
            self._clear_selection()
        self.invalidate()

    def _on_draw(self) -> None:
        if self.game.draw(self.seat) is not None:
            self.selected_index = len(self.game.hands[self.seat]) - 1

    def _on_primary_action(self) -> None:
        if self.game.can_draw(self.seat):
            self._on_draw()
            return
        selected = self._selected_tile()
        if selected is not None and self.game.discard(self.seat, selected):
            self._clear_selection()

    def _on_pong(self) -> None:
        if self.game.pong(self.seat):
            self._clear_selection()

    def _on_chi(self) -> None:
        options = self.game.chi_options(self.seat)
        if len(options) == 1 and self.game.chi(self.seat, options[0][0], options[0][1]):
            self._clear_selection()

    def _on_chi_option(self, tiles: list[str]) -> None:
        if self.game.chi(self.seat, tiles[0], tiles[1]):
            self._clear_selection()

    def _on_kong(self) -> None:
        if self.game.kong(self.seat, self._selected_tile()):
            self._clear_selection()

    def _on_hu(self) -> None:
        if self.game.hu(self.seat):
            self._clear_selection()

    async def _go_table(self) -> None:
        await self.send_command("mutgui.redirect", url="../")


# ---------------------------------------------------------------------------
# AllDebugView — 隐藏的同屏四家调试页
# ---------------------------------------------------------------------------


class AllDebugView(View):
    id = "all"
    game: MahjongGame

    game: MahjongGame
    table_view: View
    player_views: dict[Seat, View]

    def __init__(self, game: MahjongGame) -> None:
        super().__init__()
        self.game = game
        self.table_view = TableView(game, link_base="../", show_links=False)
        self.player_views = {
            seat: PlayerView(
                game,
                seat,
                view_id_prefix="all",
                show_back_button=False,
            )
            for seat in Seat
        }

    def render(self) -> ViewBlock:
        cards: list[dict[str, Any]] = []
        for seat in SEAT_ORDER:
            cards.append({
                "$component": "antd.Card",
                "$id": f"card-{seat.value}",
                "title": f"{SEAT_NAMES[seat]}家",
                "size": "small",
                "style": {"flex": "1 1 48%", "minWidth": 360},
                "$children": [self.player_views[seat]],
            })

        return ViewBlock([{
            "$component": "html.div",
            "$id": "all-wrap",
            "style": {"padding": 16, "display": "flex", "flexDirection": "column", "gap": 16},
            "$children": [{
                "$component": "html.div",
                "$id": "all-title",
                "style": {"textAlign": "center"},
                "$children": [{
                    "$component": "html.div",
                    "$id": "all-title-main",
                    "style": {"fontSize": 20, "fontWeight": "bold"},
                    "children": "麻将调试视图（all）",
                }, {
                    "$component": "html.div",
                    "$id": "all-title-sub",
                    "style": {"fontSize": 13, "color": "var(--mutgui-text-dim)", "marginTop": 4},
                    "children": "同屏观察牌桌并同时操作四家；此入口默认不在普通导航中展示。",
                }],
            }, {
                "$component": "antd.Card",
                "$id": "table-card",
                "title": "牌桌总览",
                "size": "small",
                "$children": [self.table_view],
            }, {
                "$component": "html.div",
                "$id": "players-grid",
                "style": {"display": "flex", "gap": 12, "flexWrap": "wrap"},
                "$children": cards,
            }],
        }])


# ---------------------------------------------------------------------------
# 实例化
# ---------------------------------------------------------------------------


game = MahjongGame()
table_view = TableView(game)
player_views = {seat: PlayerView(game, seat) for seat in Seat}
all_view = AllDebugView(game)

app = DemoApp([
    MutguiRoute("/", table_view, title="麻将", layout="plain"),
    *[
        MutguiRoute(f"/{seat.value}", player_views[seat], title=f"{SEAT_NAMES[seat]}家", layout="plain")
        for seat in Seat
    ],
    MutguiRoute("/all", all_view, title="麻将调试", layout="plain"),
])

if __name__ == "__main__":
    app.run()
