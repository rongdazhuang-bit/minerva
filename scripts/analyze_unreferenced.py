#!/usr/bin/env python3
"""Find likely unreferenced source files via static import graph."""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE_SRC = ROOT / "frontend/src"
BE_APP = ROOT / "backend/app"

FE_IMPORT_PATTERNS = [
    re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""import\s+['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]"""),
]
PY_IMPORT_PATTERNS = [
    re.compile(r"""from\s+([\w.]+)\s+import"""),
    re.compile(r"""import\s+([\w.]+)"""),
]
PY_FROM_IMPORT_NAMES_RE = re.compile(r"""from\s+([\w.]+)\s+import\s+([^#\n]+)""")


def _modules_from_imports(text: str) -> set[str]:
    """Collect dotted module paths from Python import statements."""

    modules: set[str] = set()
    for pattern in PY_IMPORT_PATTERNS:
        for module in pattern.findall(text):
            if module.startswith("app"):
                modules.add(module)
    for base, names_blob in PY_FROM_IMPORT_NAMES_RE.findall(text):
        if not base.startswith("app"):
            continue
        for raw_name in names_blob.split(","):
            name = raw_name.strip().split(" as ")[0].strip()
            if not name or name == "(":
                continue
            if name == "router":
                modules.add(base)
            else:
                modules.add(f"{base}.{name}")
    return modules


def fe_resolve(imp: str, base: Path) -> Path | None:
    """Resolve TS/CSS import to an existing file."""

    if imp.startswith("@/"):
        cand_base = FE_SRC / imp[2:]
    elif imp.startswith("."):
        cand_base = (base.parent / imp).resolve()
    else:
        return None

    if imp.endswith(".css"):
        return cand_base if cand_base.is_file() else None

    candidates = [
        cand_base,
        cand_base.with_suffix(".ts"),
        cand_base.with_suffix(".tsx"),
        cand_base / "index.ts",
        cand_base / "index.tsx",
        cand_base.with_suffix(".css"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def analyze_frontend() -> list[Path]:
    """Return frontend files not reachable from main/router."""

    all_files = {
        p.resolve()
        for p in FE_SRC.rglob("*")
        if p.suffix in {".ts", ".tsx", ".css"} and p.is_file()
    }
    roots = [
        FE_SRC / "main.tsx",
        FE_SRC / "app/router.tsx",
        FE_SRC / "i18n.ts",
        FE_SRC / "i18n/index.ts",
    ]
    reachable: set[Path] = set()
    queue: deque[Path] = deque(p.resolve() for p in roots if p.is_file())

    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        if current.suffix == ".css":
            continue
        try:
            text = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in FE_IMPORT_PATTERNS:
            for imp in pattern.findall(text):
                target = fe_resolve(imp, current)
                if target and target not in reachable:
                    queue.append(target)

    return sorted(all_files - reachable, key=lambda p: str(p))


def py_to_paths(module: str) -> list[Path]:
    """Map Python module name to file paths."""

    if not module.startswith("app"):
        return []
    rel = module.replace(".", "/")
    base = BE_APP.parent / rel
    paths: list[Path] = []
    py_file = base.with_suffix(".py")
    if py_file.is_file():
        paths.append(py_file.resolve())
    init_file = base / "__init__.py"
    if init_file.is_file():
        paths.append(init_file.resolve())
    return paths


def _enqueue_module(queue: deque[Path], reachable: set[Path], module: str) -> None:
    """Enqueue all file paths for a dotted module name."""

    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        sub = ".".join(parts[:end])
        for path in py_to_paths(sub):
            if path not in reachable:
                queue.append(path)


def _backend_entry_roots() -> list[Path]:
    """Collect backend analysis roots: API, Celery, and dynamic skill tools."""

    roots: list[Path] = [
        BE_APP / "main.py",
        BE_APP / "celery_app.py",
        BE_APP / "core" / "api" / "router.py",
    ]
    roots.extend(sorted(BE_APP.glob("agent/skills/*/tools.py")))
    roots.extend(sorted(BE_APP.glob("**/task/*.py")))
    roots.extend(sorted(BE_APP.glob("sys/celery/demo/*.py")))
    return [p.resolve() for p in roots if p.is_file()]


def analyze_backend() -> list[Path]:
    """Return backend app modules not reachable from API/Celery/skill entry points."""

    all_files = {
        p.resolve()
        for p in BE_APP.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.parts
    }
    reachable: set[Path] = set()
    queue: deque[Path] = deque(_backend_entry_roots())

    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        try:
            text = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        modules = _modules_from_imports(text)

        for module in modules:
            _enqueue_module(queue, reachable, module)

    return sorted(all_files - reachable, key=lambda p: str(p))


def main() -> int:
    fe_orphans = analyze_frontend()
    be_orphans = analyze_backend()

    print("=== Frontend orphans (from main.tsx + router) ===")
    print(f"Count: {len(fe_orphans)}\n")
    for path in fe_orphans:
        print(path.relative_to(ROOT))

    print("\n=== Backend orphans (from main + core/api/router + celery + skills/*/tools) ===")
    print(f"Count: {len(be_orphans)}\n")
    for path in be_orphans:
        print(path.relative_to(ROOT))

    return 0


if __name__ == "__main__":
    sys.exit(main())
