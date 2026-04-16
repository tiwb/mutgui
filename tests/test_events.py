"""事件 helpers 的单元测试。"""

from mutgui.events import TAG_KEY, bind, handler, notify


def test_notify_basic() -> None:
    result = notify(value="$0.target.value")
    assert result[TAG_KEY] == "handler"
    assert result["extract"] == {"value": "$0.target.value"}
    assert "fn" not in result


def test_notify_multiple_extract() -> None:
    result = notify(x="$0", y="$1")
    assert result["extract"] == {"x": "$0", "y": "$1"}


def test_handler_no_extract() -> None:
    fn = lambda data: None
    result = handler(fn)
    assert result[TAG_KEY] == "handler"
    assert result["fn"] is fn
    assert result["extract"] == {}


def test_handler_with_extract() -> None:
    fn = lambda data: None
    result = handler(fn, name="$0.target.value")
    assert result["fn"] is fn
    assert result["extract"] == {"name": "$0.target.value"}


def test_bind_default_path() -> None:
    obj = type("Obj", (), {"x": 0})()
    result = bind(obj, "x")
    assert result[TAG_KEY] == "bind"
    assert result["obj"] is obj
    assert result["attr"] == "x"
    assert result["path"] == "$0"


def test_bind_custom_path() -> None:
    obj = type("Obj", (), {"name": ""})()
    result = bind(obj, "name", "$0.target.value")
    assert result["path"] == "$0.target.value"
