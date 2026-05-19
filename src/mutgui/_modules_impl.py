"""ModuleRegistry 实现 — @impl for ModuleRegistry."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any

from mutobj import impl

from .modules import ModuleRegistry


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _versioned_url(
    self: ModuleRegistry, package_name: str, static_dir: Path, rel_path: str,
) -> str:
    file_path = static_dir / rel_path
    version = file_path.stat().st_mtime_ns
    return f"{self.url_prefix(package_name)}{rel_path}?v={version}"


# ---------------------------------------------------------------------------
# @impl — ModuleRegistry
# ---------------------------------------------------------------------------

@impl(ModuleRegistry.add_from_package)
def module_registry_add_from_package(self: ModuleRegistry, package_name: str) -> None:
    static_dir = importlib.resources.files(package_name) / "static"
    manifest_file = static_dir / "manifest.json"
    if not manifest_file.is_file():
        raise RuntimeError(
            f"{package_name} 缺少 static/manifest.json；"
            "请先在 frontend 目录运行 npm run build",
        )
    manifest = json.loads(manifest_file.read_text("utf-8"))
    self.packages.append((package_name, Path(str(static_dir)), manifest))


@impl(ModuleRegistry.url_prefix)
def module_registry_url_prefix(self: ModuleRegistry, package_name: str) -> str:
    return f"{self.URL_PREFIX}/{package_name}/"


@impl(ModuleRegistry.url_for)
def module_registry_url_for(
    self: ModuleRegistry, package_name: str, rel_path: str,
) -> str:
    for current_name, static_dir, _manifest in self.packages:
        if current_name == package_name:
            return _versioned_url(self, package_name, static_dir, rel_path)
    raise KeyError(f"Unknown package in ModuleRegistry: {package_name}")


@impl(ModuleRegistry.static_mounts)
def module_registry_static_mounts(self: ModuleRegistry) -> list[tuple[str, Path]]:
    return [
        (self.url_prefix(package_name).rstrip("/"), static_dir)
        for package_name, static_dir, _manifest in self.packages
    ]


@impl(ModuleRegistry.runtime_manifest)
def module_registry_runtime_manifest(self: ModuleRegistry) -> dict[str, Any]:
    import_map: dict[str, str] = {}
    css: list[str] = []
    entries: list[dict[str, str]] = []
    for package_name, static_dir, manifest in self.packages:
        for name, rel_path in manifest.get("exports", {}).items():
            if name in import_map:
                raise RuntimeError(
                    f"Import name conflict: {name!r} already provided by another package",
                )
            import_map[name] = _versioned_url(
                self, package_name, static_dir, rel_path,
            )
        for rel_path in manifest.get("css", []):
            css.append(_versioned_url(self, package_name, static_dir, rel_path))
        for entry in manifest.get("entries", []):
            entries.append(entry)
    return {
        "importMap": import_map,
        "css": css,
        "entries": entries,
    }
