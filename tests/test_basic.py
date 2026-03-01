"""基础测试 - 确认包可以正常导入。"""


def test_import() -> None:
    import mutgui
    assert mutgui.__version__


def test_version_format() -> None:
    import mutgui
    parts = mutgui.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
