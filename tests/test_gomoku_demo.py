"""gomoku demo 测试。"""

import random

from demo.games.gomoku import BOARD_SIZE, GomokuGame, GomokuView, Move, Stone, app


def make_game() -> GomokuGame:
    game = GomokuGame()
    game.ai_stones.clear()
    return game


def test_place_alternates_turn_and_detects_horizontal_win() -> None:
    game = make_game()

    moves = [
        (7, 3), (6, 3),
        (7, 4), (6, 4),
        (7, 5), (6, 5),
        (7, 6), (6, 6),
        (7, 7),
    ]
    for row, col in moves:
        assert game.place(row, col) is True

    assert game.winner is Stone.BLACK
    assert len(game.winning_line) >= 5
    assert game.status_text() == "黑方获胜"


def test_undo_restores_turn_and_clears_board_position() -> None:
    game = make_game()
    assert game.place(7, 7) is True
    assert game.place(7, 8) is True

    assert game.undo() is True
    assert game.cell(7, 8) is None
    assert game.current_stone is Stone.WHITE
    assert game.winner is None


def test_ai_blocks_opponent_immediate_five() -> None:
    game = make_game()
    for col in range(4):
        game.board[7][col] = Stone.BLACK
        game.history.append(Move(7, col, Stone.BLACK))
    game.current_stone = Stone.WHITE
    game.ai_stones = {Stone.WHITE}

    assert game.run_ai_step() is True
    assert game.cell(7, 4) is Stone.WHITE
    assert game.current_stone is Stone.BLACK


def test_ai_blocks_open_three_before_it_becomes_forced_loss() -> None:
    game = make_game()
    game._rng = random.Random(0)
    game.board[7][6] = Stone.BLACK
    game.board[7][7] = Stone.BLACK
    game.board[7][8] = Stone.BLACK
    game.board[6][6] = Stone.WHITE
    game.board[6][7] = Stone.WHITE
    game.history = [
        Move(7, 6, Stone.BLACK),
        Move(6, 6, Stone.WHITE),
        Move(7, 7, Stone.BLACK),
        Move(6, 7, Stone.WHITE),
        Move(7, 8, Stone.BLACK),
    ]
    game.current_stone = Stone.WHITE
    game.ai_stones = {Stone.WHITE}

    assert game.run_ai_step() is True
    assert game.last_move() is not None
    assert (game.last_move().row, game.last_move().col) in {(7, 5), (7, 9)}


def test_ai_opening_prefers_exact_center() -> None:
    game = make_game()
    game.ai_stones = {Stone.BLACK}

    assert game.run_ai_step() is True
    assert game.last_move() == Move(7, 7, Stone.BLACK)


def test_view_renders_controls_and_full_board_grid() -> None:
    game = make_game()
    view = GomokuView(game)
    tree = view.render().items

    controls = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "controls")
    assert [child["children"] for child in controls["$children"]] == ["重开", "悔棋", "切黑AI", "切白AI"]

    board_wrap = next(node for node in tree if isinstance(node, dict) and node.get("$id") == "board-wrap")
    board_grid = board_wrap["$children"][0]
    assert board_grid["$id"] == "board-grid"
    assert len(board_grid["$children"]) == BOARD_SIZE * BOARD_SIZE


def test_gomoku_app_has_root_route() -> None:
    assert [route.path for route in app.routes] == ["/"]
