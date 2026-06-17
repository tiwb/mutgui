import pytest
from mutobj.lint import check


def test_lint() -> None:
    results = check(["mutgui.*", "demo.*"])
    if results:
        pytest.fail(results.format())
