from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from promptcrab.errors import PipelineError

UNRELEASED_PLACEHOLDER = "- No unreleased changes yet."

CALVER_RE = re.compile(
    r"^(?P<year>\d{4})\.(?P<month>\d{1,2})\.(?P<day>\d{1,2})"
    r"(?:-(?P<suffix>[0-9]+|beta\.[0-9]+))?$"
)


@dataclass(frozen=True, slots=True)
class CalVer:
    year: int
    month: int
    day: int
    suffix: str | None = None

    @property
    def release_date(self) -> date:
        return date(self.year, self.month, self.day)

    @property
    def base(self) -> str:
        return f"{self.year}.{self.month}.{self.day}"

    def __str__(self) -> str:
        return self.base if self.suffix is None else f"{self.base}-{self.suffix}"


def parse_calver(version: str) -> CalVer:
    match = CALVER_RE.fullmatch(version)
    if match is None:
        raise PipelineError(
            "Invalid CalVer. Expected YYYY.M.D, YYYY.M.D-<n>, or YYYY.M.D-beta.<n>."
        )

    try:
        release_date = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as exc:
        raise PipelineError(f"Invalid calendar date in version: {version}") from exc

    return CalVer(
        year=release_date.year,
        month=release_date.month,
        day=release_date.day,
        suffix=match.group("suffix"),
    )


def bump_calver(
    current_version: str,
    *,
    target_date: date,
    kind: str = "stable",
    explicit_version: str | None = None,
) -> str:
    if explicit_version is not None:
        return str(parse_calver(explicit_version))

    current = parse_calver(current_version)
    base = f"{target_date.year}.{target_date.month}.{target_date.day}"

    if kind == "beta":
        if (
            current.release_date == target_date
            and current.suffix
            and current.suffix.startswith("beta.")
        ):
            beta_number = int(current.suffix.removeprefix("beta."))
            return f"{base}-beta.{beta_number + 1}"
        return f"{base}-beta.1"

    if kind != "stable":
        raise PipelineError(f"Unsupported bump kind: {kind}")

    if current.release_date < target_date:
        return base

    if current.release_date > target_date:
        raise PipelineError(
            "Current version "
            f"{current_version} is newer than target date {target_date.isoformat()}."
        )

    if current.suffix is None:
        return f"{base}-1"

    if current.suffix.startswith("beta."):
        return base

    return f"{base}-{int(current.suffix) + 1}"


def update_about_text(about_text: str, new_version: str) -> str:
    parse_calver(new_version)
    updated, count = re.subn(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{new_version}"',
        about_text,
        count=1,
    )
    if count != 1:
        raise PipelineError("Could not update __version__ in __about__.py")
    return updated


def cut_release_in_changelog(changelog_text: str, version: str, *, released_on: date) -> str:
    parse_calver(version)

    unreleased_heading = "## Unreleased"
    released_heading = f"## [{version}] - {released_on.isoformat()}"

    if released_heading in changelog_text:
        raise PipelineError(f"Changelog already contains a section for {version}")

    if unreleased_heading not in changelog_text:
        raise PipelineError("CHANGELOG.md must contain a '## Unreleased' section.")

    before, after = changelog_text.split(unreleased_heading, 1)
    next_section_index = after.find("\n## ")
    if next_section_index == -1:
        unreleased_body = after
        remainder = ""
    else:
        unreleased_body = after[:next_section_index]
        remainder = after[next_section_index:]

    unreleased_body = unreleased_body.strip()
    if not unreleased_body or unreleased_body == UNRELEASED_PLACEHOLDER:
        release_body = "- No user-facing changes were recorded for this release."
    else:
        release_body = unreleased_body

    return (
        f"{before}{unreleased_heading}\n\n{UNRELEASED_PLACEHOLDER}\n\n"
        f"{released_heading}\n\n{release_body}\n"
        f"{remainder}"
    ).rstrip() + "\n"


def extract_release_notes(changelog_text: str, version: str) -> str:
    parse_calver(version)
    heading = f"## [{version}]"
    start = changelog_text.find(heading)
    if start == -1:
        raise PipelineError(
            f"Could not find release notes for version {version} in CHANGELOG.md"
        )

    section_start = changelog_text.find("\n", start)
    if section_start == -1:
        raise PipelineError(f"Malformed CHANGELOG.md section for version {version}")
    section_start += 1

    next_section = changelog_text.find("\n## ", section_start)
    if next_section == -1:
        notes = changelog_text[section_start:]
    else:
        notes = changelog_text[section_start:next_section]
    return notes.strip() + "\n"
