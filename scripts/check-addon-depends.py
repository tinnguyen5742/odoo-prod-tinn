#!/usr/bin/env python3
"""Fail if a custom addon's manifest depends on a module that is not on addons_path.

Odoo only loads modules that are direct children of an addons_path entry.
This reads /etc/odoo/odoo.conf (image default), scans those directories, and
checks `depends` on every module under /mnt/extra-addons.

Used by .github/workflows/docker-publish.yml after the image is loaded.
No database. Stdlib only.

  python3 check-addon-depends.py
  python3 check-addon-depends.py --conf /etc/odoo/odoo.conf
  python3 check-addon-depends.py --addons-path /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

DEFAULT_CONF = "/etc/odoo/odoo.conf"
CUSTOM_ROOT = Path("/mnt/extra-addons")
MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--conf", default=DEFAULT_CONF)
    p.add_argument(
        "--addons-path",
        default="",
        help="Comma-separated addons_path. Overrides --conf when set.",
    )
    p.add_argument(
        "--custom-root",
        default=str(CUSTOM_ROOT),
        help="Only modules under this directory are checked for missing depends.",
    )
    return p.parse_args(argv)


def addons_path_from_conf(conf: Path) -> list[str]:
    if not conf.is_file():
        raise SystemExit(f"check-addon-depends: no config file: {conf}")
    found: list[str] | None = None
    for raw in conf.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("addons_path"):
            _, _, val = line.partition("=")
            if not val.strip() and " " in line:
                _, _, val = line.partition(" ")
            found = [p.strip() for p in val.split(",") if p.strip()]
    if not found:
        raise SystemExit(f"check-addon-depends: no addons_path in {conf}")
    return found


def manifest_file(module_dir: Path) -> Path | None:
    for name in MANIFEST_NAMES:
        path = module_dir / name
        if path.is_file():
            return path
    return None


def scan_modules(entries: list[str]) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = {}
    for entry in entries:
        root = Path(entry)
        if not root.is_dir():
            print(f"check-addon-depends: addons_path entry missing: {entry}", file=sys.stderr)
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if manifest_file(child) is None:
                continue
            by_name.setdefault(child.name, []).append(child)
    return by_name


def depends_of(manifest: Path) -> list[str]:
    tree = ast.parse(manifest.read_text(encoding="utf-8"), filename=str(manifest))
    for node in tree.body:
        value = None
        if isinstance(node, ast.Expr):
            value = node.value
        elif isinstance(node, ast.Assign):
            value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for key, val in zip(value.keys, value.values):
            if not isinstance(key, ast.Constant) or key.value != "depends":
                continue
            if not isinstance(val, ast.List):
                raise SystemExit(f"check-addon-depends: {manifest}: depends is not a list")
            deps: list[str] = []
            for elt in val.elts:
                if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                    raise SystemExit(f"check-addon-depends: {manifest}: depends entries must be strings")
                deps.append(elt.value)
            return deps
    return []


def is_custom(module_dir: Path, custom_root: Path) -> bool:
    try:
        module_dir.resolve().relative_to(custom_root.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    custom_root = Path(args.custom_root)
    if args.addons_path:
        entries = [p.strip() for p in args.addons_path.split(",") if p.strip()]
    else:
        entries = addons_path_from_conf(Path(args.conf))

    print("addons_path = " + ",".join(entries))
    by_name = scan_modules(entries)
    if not by_name:
        print("check-addon-depends: no modules on addons_path", file=sys.stderr)
        return 1

    available = set(by_name)
    status = 0

    duplicates = sorted(name for name, paths in by_name.items() if len(paths) > 1)
    if duplicates:
        status = 1
        print("Duplicate module names on addons_path:")
        for name in duplicates:
            for path in by_name[name]:
                print(f"  {name}  {path}")

    custom = sorted(
        (name, paths[0])
        for name, paths in by_name.items()
        if is_custom(paths[0], custom_root)
    )
    if not custom:
        print(f"check-addon-depends: no modules under {custom_root}", file=sys.stderr)
        return 1

    missing_rows: list[tuple[str, str]] = []
    for name, path in custom:
        manifest = manifest_file(path)
        if manifest is None:
            continue
        for dep in depends_of(manifest):
            if dep not in available:
                missing_rows.append((name, dep))

    if missing_rows:
        status = 1
        print("Missing depends (module -> required):")
        for name, dep in missing_rows:
            print(f"  {name} -> {dep}")

    print(f"Checked {len(custom)} custom modules against {len(available)} modules on addons_path")
    if status == 0:
        print("Addon depends are complete")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
