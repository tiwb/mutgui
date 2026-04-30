"""五子棋 demo — 15x15 棋盘 + 悔棋 + 黑白 AI 托管。"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mutgui import Callback, View, ViewBlock

from demo.framework import DemoApp, MutguiRoute


BOARD_SIZE = 15
WIN_LENGTH = 5
AI_MOVE_DELAY_SECONDS = 1.0
BOARD_CELL_SIZE = "clamp(22px, 5.8vw, 38px)"
STONE_SIZE = "clamp(16px, 4.2vw, 28px)"


class Stone(Enum):
    BLACK = "black"
    WHITE = "white"

    @property
    def other(self) -> Stone:
        return Stone.WHITE if self is Stone.BLACK else Stone.BLACK


STONE_NAMES = {
    Stone.BLACK: "黑方",
    Stone.WHITE: "白方",
}

STONE_TEXT = {
    Stone.BLACK: "●",
    Stone.WHITE: "●",
}

CellPos = tuple[int, int]
JsonBlock = dict[str, Any]


@dataclass(frozen=True)
class Move:
    row: int
    col: int
    stone: Stone


class GomokuGame:
    def __init__(self) -> None:
        self.board: list[list[Stone | None]] = []
        self.current_stone = Stone.BLACK
        self.winner: Stone | None = None
        self.winning_line: set[CellPos] = set()
        self.history: list[Move] = []
        self.ai_stones: set[Stone] = set()
        self._on_change: list[Callable[[], None]] = []
        self._ai_task: asyncio.Task[None] | None = None
        self._rng = random.Random()
        self.ai = GomokuAi(self)
        self.reset()

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change.append(callback)

    def reset(self) -> None:
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_stone = Stone.BLACK
        self.winner = None
        self.winning_line.clear()
        self.history = []
        self._notify()

    def _notify(self) -> None:
        for callback in self._on_change:
            callback()
        self._schedule_ai_action()

    def is_ai(self, stone: Stone) -> bool:
        return stone in self.ai_stones

    def toggle_ai(self, stone: Stone) -> None:
        if stone in self.ai_stones:
            self.ai_stones.remove(stone)
        else:
            self.ai_stones.add(stone)
        self._notify()

    def cell(self, row: int, col: int) -> Stone | None:
        return self.board[row][col]

    def last_move(self) -> Move | None:
        return self.history[-1] if self.history else None

    def is_draw(self) -> bool:
        return self.winner is None and len(self.history) == BOARD_SIZE * BOARD_SIZE

    def is_waiting_for_ai(self) -> bool:
        return self.winner is None and not self.is_draw() and self.is_ai(self.current_stone)

    def status_text(self) -> str:
        if self.winner is not None:
            return f"{STONE_NAMES[self.winner]}获胜"
        if self.is_draw():
            return "平局"
        suffix = "（AI 思考中）" if self.is_waiting_for_ai() else ""
        return f"轮到{STONE_NAMES[self.current_stone]}落子{suffix}"

    def can_place(self, row: int, col: int, *, by_ai: bool = False) -> bool:
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return False
        if self.winner is not None or self.is_draw() or self.board[row][col] is not None:
            return False
        if not by_ai and self.is_waiting_for_ai():
            return False
        return True

    def place(self, row: int, col: int, *, by_ai: bool = False) -> bool:
        if not self.can_place(row, col, by_ai=by_ai):
            return False
        stone = self.current_stone
        self.board[row][col] = stone
        self.history.append(Move(row, col, stone))
        line = self._find_winning_line(row, col, stone)
        if line:
            self.winner = stone
            self.winning_line = set(line)
        elif not self.is_draw():
            self.current_stone = stone.other
        self._notify()
        return True

    def undo(self) -> bool:
        if not self.history:
            return False
        last = self.history.pop()
        self.board[last.row][last.col] = None
        self.current_stone = last.stone
        self.winner = None
        self.winning_line.clear()
        self._notify()
        return True

    def run_ai_step(self) -> bool:
        move = self.ai.choose_move()
        if move is None:
            return False
        return self.place(move[0], move[1], by_ai=True)

    def _schedule_ai_action(self) -> None:
        if not self.is_waiting_for_ai():
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
            await asyncio.sleep(AI_MOVE_DELAY_SECONDS)
        except asyncio.CancelledError:
            return
        self._ai_task = None
        self.run_ai_step()

    def _find_winning_line(self, row: int, col: int, stone: Stone) -> list[CellPos] | None:
        for delta_row, delta_col in ((1, 0), (0, 1), (1, 1), (1, -1)):
            negative = self._collect_direction(row, col, stone, -delta_row, -delta_col)
            positive = self._collect_direction(row, col, stone, delta_row, delta_col)
            line = list(reversed(negative)) + [(row, col)] + positive
            if len(line) >= WIN_LENGTH:
                return line
        return None

    def _collect_direction(
        self,
        row: int,
        col: int,
        stone: Stone,
        delta_row: int,
        delta_col: int,
    ) -> list[CellPos]:
        positions: list[CellPos] = []
        next_row = row + delta_row
        next_col = col + delta_col
        while 0 <= next_row < BOARD_SIZE and 0 <= next_col < BOARD_SIZE and self.board[next_row][next_col] is stone:
            positions.append((next_row, next_col))
            next_row += delta_row
            next_col += delta_col
        return positions


class GomokuAi:
    def __init__(self, game: GomokuGame) -> None:
        self.game = game

    def choose_move(self) -> CellPos | None:
        game = self.game
        if not game.is_waiting_for_ai():
            return None
        candidates = self._candidate_positions()
        if not candidates:
            return None
        if not game.history:
            center = BOARD_SIZE // 2
            return (center, center)

        winning_moves = [(row, col) for row, col in candidates if self._would_win(row, col, game.current_stone)]
        if winning_moves:
            return self._choose_among(winning_moves)

        opponent = game.current_stone.other
        forced_blocks = [(row, col) for row, col in candidates if self._would_win(row, col, opponent)]
        if forced_blocks:
            return self._choose_among(forced_blocks)

        ranked = sorted(
            ((self._evaluate_move(row, col, game.current_stone), (row, col)) for row, col in candidates),
            reverse=True,
            key=lambda item: item[0],
        )
        return self._pick_ranked_move(ranked)

    def _candidate_positions(self) -> list[CellPos]:
        game = self.game
        if not game.history:
            center = BOARD_SIZE // 2
            return [(center, center)]

        candidates: set[CellPos] = set()
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if game.board[row][col] is None:
                    continue
                for next_row in range(max(0, row - 2), min(BOARD_SIZE, row + 3)):
                    for next_col in range(max(0, col - 2), min(BOARD_SIZE, col + 3)):
                        if game.board[next_row][next_col] is None:
                            candidates.add((next_row, next_col))
        return sorted(candidates)

    def _choose_among(self, positions: list[CellPos]) -> CellPos | None:
        if not positions:
            return None
        return self.game._rng.choice(positions)

    def _pick_ranked_move(self, ranked: list[tuple[tuple[float, float, float, float], CellPos]]) -> CellPos | None:
        if not ranked:
            return None
        best_score = ranked[0][0]
        close_moves = [ranked[0][1]]
        for score, pos in ranked[1:4]:
            if score[0] != best_score[0]:
                break
            if score[1] < best_score[1] - 120:
                continue
            if score[2] < best_score[2] - 160:
                continue
            close_moves.append(pos)
        return self._choose_among(close_moves)

    def _would_win(self, row: int, col: int, stone: Stone) -> bool:
        game = self.game
        if game.board[row][col] is not None:
            return False
        game.board[row][col] = stone
        try:
            return game._find_winning_line(row, col, stone) is not None
        finally:
            game.board[row][col] = None

    def _evaluate_move(self, row: int, col: int, stone: Stone) -> tuple[float, float, float, float]:
        game = self.game
        opponent = stone.other
        own_score = self._score_position(row, col, stone)
        block_score = self._score_position(row, col, opponent)
        center = BOARD_SIZE // 2

        game.board[row][col] = stone
        try:
            opponent_immediate_wins = 0
            opponent_best_score = 0.0
            self_followup_score = 0.0
            for next_row, next_col in self._candidate_positions():
                if self._would_win(next_row, next_col, opponent):
                    opponent_immediate_wins += 1
                opponent_best_score = max(opponent_best_score, self._score_position(next_row, next_col, opponent))
                self_followup_score = max(self_followup_score, self._score_position(next_row, next_col, stone))
        finally:
            game.board[row][col] = None

        return (
            -float(opponent_immediate_wins),
            -opponent_best_score,
            self_followup_score + block_score * 1.2,
            own_score - self._distance_to_center(row, col, center) * 0.01,
        )

    def _score_position(self, row: int, col: int, stone: Stone) -> float:
        game = self.game
        if game.board[row][col] is not None:
            return -1.0

        total = 0.0
        for delta_row, delta_col in ((1, 0), (0, 1), (1, 1), (1, -1)):
            total += self._direction_score(row, col, stone, delta_row, delta_col)
        total += self._neighbor_bonus(row, col, stone)
        return total

    def _direction_score(self, row: int, col: int, stone: Stone, delta_row: int, delta_col: int) -> float:
        total_count = 1
        open_ends = 0
        for sign in (-1, 1):
            count, is_open = self._scan_line(row, col, stone, delta_row * sign, delta_col * sign)
            total_count += count
            if is_open:
                open_ends += 1

        if total_count >= 5:
            return 100000.0
        if total_count == 4:
            return 18000.0 if open_ends == 2 else 4000.0
        if total_count == 3:
            return 1500.0 if open_ends == 2 else 180.0
        if total_count == 2:
            return 160.0 if open_ends == 2 else 30.0
        return 8.0 if open_ends == 2 else 2.0

    def _scan_line(self, row: int, col: int, stone: Stone, delta_row: int, delta_col: int) -> tuple[int, bool]:
        game = self.game
        count = 0
        next_row = row + delta_row
        next_col = col + delta_col
        while 0 <= next_row < BOARD_SIZE and 0 <= next_col < BOARD_SIZE and game.board[next_row][next_col] is stone:
            count += 1
            next_row += delta_row
            next_col += delta_col
        is_open = 0 <= next_row < BOARD_SIZE and 0 <= next_col < BOARD_SIZE and game.board[next_row][next_col] is None
        return count, is_open

    def _neighbor_bonus(self, row: int, col: int, stone: Stone) -> float:
        game = self.game
        bonus = 0.0
        for next_row in range(max(0, row - 1), min(BOARD_SIZE, row + 2)):
            for next_col in range(max(0, col - 1), min(BOARD_SIZE, col + 2)):
                if next_row == row and next_col == col:
                    continue
                cell = game.board[next_row][next_col]
                if cell is stone:
                    bonus += 18.0
                elif cell is stone.other:
                    bonus += 10.0
        return bonus

    def _distance_to_center(self, row: int, col: int, center: int) -> int:
        return abs(row - center) + abs(col - center)


def button(
    button_id: str,
    label: str,
    on_click: Callback,
    *,
    disabled: bool = False,
    button_type: str | None = None,
) -> JsonBlock:
    result: JsonBlock = {
        "$component": "antd.Button",
        "$id": button_id,
        "children": label,
        "disabled": disabled,
        "onClick": on_click,
    }
    if button_type is not None:
        result["type"] = button_type
    return result


class GomokuView(View):
    id = "board"

    def __init__(self, game: GomokuGame) -> None:
        super().__init__()
        self.game = game
        game.on_change(self.invalidate)

    def render(self) -> ViewBlock:
        return ViewBlock([
            self._title_block(),
            self._controls_block(),
            self._board_wrap(),
            self._legend_block(),
        ])

    def _title_block(self) -> JsonBlock:
        return {
            "$component": "div",
            "$id": "title",
            "style": {"textAlign": "center", "marginBottom": 16},
            "$children": [{
                "$component": "div",
                "$id": "title-main",
                "style": {"fontSize": 26, "fontWeight": "bold", "marginBottom": 6},
                "children": "五子棋",
            }, {
                "$component": "div",
                "$id": "title-sub",
                "style": {"fontSize": 14, "color": "var(--mutgui-text-dim)"},
                "children": f"{self.game.status_text()} · 共 {len(self.game.history)} 手",
            }],
        }

    def _controls_block(self) -> JsonBlock:
        return {
            "$component": "div",
            "$id": "controls",
            "style": {"display": "flex", "gap": 8, "flexWrap": "wrap", "marginBottom": 14, "justifyContent": "center"},
            "$children": [
                button("reset", "重开", Callback(self._on_reset), button_type="primary"),
                button("undo", "悔棋", Callback(self._on_undo), disabled=not self.game.history),
                button(
                    "ai-black",
                    "切回黑方人工" if self.game.is_ai(Stone.BLACK) else "切黑AI",
                    Callback(lambda: self._on_toggle_ai(Stone.BLACK)),
                ),
                button(
                    "ai-white",
                    "切回白方人工" if self.game.is_ai(Stone.WHITE) else "切白AI",
                    Callback(lambda: self._on_toggle_ai(Stone.WHITE)),
                ),
            ],
        }

    def _board_wrap(self) -> JsonBlock:
        return {
            "$component": "div",
            "$id": "board-wrap",
            "style": {"overflowX": "auto", "paddingBottom": 8},
            "$children": [{
                "$component": "div",
                "$id": "board-grid",
                "style": {
                    "display": "grid",
                    "gridTemplateColumns": f"repeat({BOARD_SIZE}, {BOARD_CELL_SIZE})",
                    "gridTemplateRows": f"repeat({BOARD_SIZE}, {BOARD_CELL_SIZE})",
                    "gap": 1,
                    "justifyContent": "center",
                    "width": "max-content",
                    "margin": "0 auto",
                    "padding": 6,
                    "background": "#8c6239",
                    "borderRadius": 12,
                    "boxShadow": "0 8px 24px rgba(0, 0, 0, 0.12)",
                },
                "$children": [self._cell_block(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)],
            }],
        }

    def _cell_block(self, row: int, col: int) -> JsonBlock:
        cell = self.game.cell(row, col)
        move = self.game.last_move()
        is_last_move = move is not None and move.row == row and move.col == col
        is_winning_cell = (row, col) in self.game.winning_line
        clickable = self.game.can_place(row, col)
        text = STONE_TEXT[cell] if cell is not None else ""
        style: dict[str, Any] = {
            "width": BOARD_CELL_SIZE,
            "height": BOARD_CELL_SIZE,
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "background": "#d9b06f" if not is_winning_cell else "#ffd666",
            "border": "1px solid rgba(80, 52, 24, 0.42)",
            "fontSize": STONE_SIZE,
            "lineHeight": 1,
            "cursor": "pointer" if clickable else "default",
            "userSelect": "none",
            "boxSizing": "border-box",
        }
        if is_last_move:
            style["outline"] = "2px solid #1677ff"
            style["outlineOffset"] = "-2px"
        if cell is Stone.BLACK:
            style["color"] = "#111111"
        elif cell is Stone.WHITE:
            style["color"] = "#f8f8f8"
            style["textShadow"] = "0 0 1px rgba(0, 0, 0, 0.9), 0 0 3px rgba(0, 0, 0, 0.45)"
        elif clickable:
            style["color"] = "rgba(0, 0, 0, 0.14)"
        return {
            "$component": "div",
            "$id": f"cell-{row}-{col}",
            "style": style,
            "children": text,
            "onClick": Callback(lambda r=row, c=col: self._on_place(r, c)),
        }

    def _legend_block(self) -> JsonBlock:
        last = self.game.last_move()
        last_text = "无" if last is None else f"{STONE_NAMES[last.stone]} ({last.row + 1}, {last.col + 1})"
        return {
            "$component": "div",
            "$id": "legend",
            "style": {
                "marginTop": 12,
                "textAlign": "center",
                "fontSize": 13,
                "color": "var(--mutgui-text-dim)",
                "lineHeight": 1.7,
            },
            "$children": [{
                "$component": "div",
                "$id": "legend-line-1",
                "children": "点击空位直接落子；先连成五子者获胜。",
            }, {
                "$component": "div",
                "$id": "legend-line-2",
                "children": f"最后一手：{last_text}",
            }],
        }

    def _on_place(self, row: int, col: int) -> None:
        self.game.place(row, col)

    def _on_reset(self) -> None:
        self.game.reset()

    def _on_undo(self) -> None:
        self.game.undo()

    def _on_toggle_ai(self, stone: Stone) -> None:
        self.game.toggle_ai(stone)


game = GomokuGame()
board_view = GomokuView(game)

app = DemoApp([
    MutguiRoute("/", board_view, title="五子棋", layout="plain"),
])


if __name__ == "__main__":
    app.run()
