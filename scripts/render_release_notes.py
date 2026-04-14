#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from promptcrab.release_tools import extract_release_notes

CHANGELOG_PATH = Path("CHANGELOG.md")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render release notes for a version from CHANGELOG.md"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Release version, for example 2026.4.14",
    )
    parser.add_argument("--output", help="Optional output file. Defaults to stdout.")
    return parser


def main() -> int:
    args = make_parser().parse_args()
    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    notes = extract_release_notes(changelog_text, args.version)

    if args.output:
        Path(args.output).write_text(notes, encoding="utf-8")
    else:
        print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
