"""前端模块 registry 与 runtime manifest 聚合。"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any


class ModuleRegistry:
    """聚合 Python 包内的前端 manifest，并生成运行时 import map。"""

    URL_PREFIX = "/static/modules"

    def __init__(self) -> None:
        self._packages: list[tuple[str, Path, dict[str, Any]]] = []

    def add_from_package(self, package_name: str) -> None:
        static_dir = importlib.resources.files(package_name) / "static"
        manifest_file = static_dir / "manifest.json"
        if not manifest_file.is_file():
            raise RuntimeError(
                f"{package_name} 缺少 static/manifest.json；"
                "请先在 frontend 目录运行 npm run build",
            )
        manifest = json.loads(manifest_file.read_text("utf-8"))
        self._packages.append((package_name, Path(str(static_dir)), manifest))

    def url_prefix(self, package_name: str) -> str:
        return f"{self.URL_PREFIX}/{package_name}/"

    def _versioned_url(self, package_name: str, static_dir: Path, rel_path: str) -> str:
        file_path = static_dir / rel_path
        version = file_path.stat().st_mtime_ns
        return f"{self.url_prefix(package_name)}{rel_path}?v={version}"

    def static_mounts(self) -> list[tuple[str, Path]]:
        return [
            (self.url_prefix(package_name).rstrip("/"), static_dir)
            for package_name, static_dir, _manifest in self._packages
        ]

    def runtime_manifest(self) -> dict[str, Any]:
        import_map: dict[str, str] = {}
        css: list[str] = []
        entries: list[dict[str, str]] = []
        for package_name, static_dir, manifest in self._packages:
            for name, rel_path in manifest.get("exports", {}).items():
                if name in import_map:
                    raise RuntimeError(
                        f"Import name conflict: {name!r} already provided by another package",
                    )
                import_map[name] = self._versioned_url(package_name, static_dir, rel_path)
            for rel_path in manifest.get("css", []):
                css.append(self._versioned_url(package_name, static_dir, rel_path))
            for entry in manifest.get("entries", []):
                entries.append(entry)
        return {
            "importMap": import_map,
            "css": css,
            "entries": entries,
        }
