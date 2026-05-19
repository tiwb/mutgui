"""前端模块 registry 与 runtime manifest 聚合。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mutobj


class ModuleRegistry(mutobj.Declaration):
    """聚合 Python 包内的前端 manifest，并生成运行时 import map。"""

    URL_PREFIX = "/static/modules"
    packages: list[tuple[str, Path, dict[str, Any]]] = mutobj.field(default_factory=list)

    def add_from_package(self, package_name: str) -> None:
        """读取包内的 static/manifest.json，注册前端模块。"""
        ...

    def url_prefix(self, package_name: str) -> str:
        """返回包的静态资源 URL 前缀。"""
        ...

    def url_for(self, package_name: str, rel_path: str) -> str:
        """返回指定包的某个文件的带版本号 URL。"""
        ...

    def static_mounts(self) -> list[tuple[str, Path]]:
        """返回所有注册包的 (URL 前缀, 静态目录) 对。"""
        ...

    def runtime_manifest(self) -> dict[str, Any]:
        """生成运行时 import map、CSS 列表、entry 列表。"""
        ...


from . import _modules_impl as _modules_impl  # noqa: E402, F401
