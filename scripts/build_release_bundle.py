#!/usr/bin/env python3
"""Build a clean release bundle for end users."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
RELEASE_TEMPLATE = ROOT_DIR / "release" / "README.bundle.md"
RUNTIME_FILES = [
    "seo_exporter.py",
    "cli.py",
    "config.py",
    "db.py",
    "exporter.py",
    "requirements.txt",
    "config.example.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a clean release bundle for SEO Exporter.")
    parser.add_argument("--version", required=True, help="Release version, for example v1.0.0-rc1.")
    return parser.parse_args()


def build_bundle(version: str) -> Path:
    bundle_dir = DIST_DIR / f"seo-exporter-{version}"
    archive_path = DIST_DIR / f"seo-exporter-{version}.zip"

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if archive_path.exists():
        archive_path.unlink()

    bundle_dir.mkdir(parents=True, exist_ok=True)

    for relative_path in RUNTIME_FILES:
        source_path = ROOT_DIR / relative_path
        target_path = bundle_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    readme_text = RELEASE_TEMPLATE.read_text(encoding="utf-8").replace("{{VERSION}}", version)
    (bundle_dir / "README.md").write_text(readme_text, encoding="utf-8")

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(bundle_dir.parent))

    return bundle_dir


def main() -> int:
    args = parse_args()
    bundle_dir = build_bundle(args.version)
    print(f"✅ Release bundle created: {bundle_dir}")
    print(f"✅ Zip archive created: {bundle_dir}.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
