#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from promptcrab.release_tools import bump_calver, cut_release_in_changelog, update_about_text

ABOUT_PATH = Path("src/promptcrab/__about__.py")
CHANGELOG_PATH = Path("CHANGELOG.md")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bump promptcrab CalVer and cut a changelog release."
    )
    parser.add_argument(
        "--kind",
        choices=["stable", "beta"],
        default="stable",
        help="Version bump kind when no explicit version is provided.",
    )
    parser.add_argument(
        "--date",
        dest="release_date",
        help="Release date in YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--version",
        help="Explicit target version, for example 2026.4.14 or 2026.4.14-beta.1.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the computed version without modifying files.",
    )
    return parser


def main() -> int:
    args = make_parser().parse_args()
    target_date = date.fromisoformat(args.release_date) if args.release_date else date.today()

    current_about = ABOUT_PATH.read_text(encoding="utf-8")
    current_version = current_about.split('"')[1]
    new_version = bump_calver(
        current_version,
        target_date=target_date,
        kind=args.kind,
        explicit_version=args.version,
    )

    if args.dry_run:
        print(new_version)
        return 0

    ABOUT_PATH.write_text(
        update_about_text(current_about, new_version),
        encoding="utf-8",
    )

    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    CHANGELOG_PATH.write_text(
        cut_release_in_changelog(changelog_text, new_version, released_on=target_date),
        encoding="utf-8",
    )

    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
