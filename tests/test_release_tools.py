from datetime import date

from promptcrab.release_tools import (
    bump_calver,
    cut_release_in_changelog,
    extract_release_notes,
    update_about_text,
)


def test_bump_calver_moves_to_same_day_followup_release() -> None:
    result = bump_calver(
        "2026.4.14",
        target_date=date(2026, 4, 14),
    )

    assert result == "2026.4.14-1"


def test_bump_calver_increments_beta_series() -> None:
    result = bump_calver(
        "2026.4.14-beta.1",
        target_date=date(2026, 4, 14),
        kind="beta",
    )

    assert result == "2026.4.14-beta.2"


def test_update_about_text_rewrites_version_literal() -> None:
    updated = update_about_text('__version__ = "2026.4.14"\n', "2026.4.14-1")

    assert updated == '__version__ = "2026.4.14-1"\n'


def test_cut_release_in_changelog_moves_unreleased_section() -> None:
    changelog = """# Changelog

## Unreleased

### Fixed

- Preserve API keys in rewrites.
"""

    updated = cut_release_in_changelog(
        changelog,
        "2026.4.15",
        released_on=date(2026, 4, 15),
    )

    assert "## [2026.4.15] - 2026-04-15" in updated
    assert "- Preserve API keys in rewrites." in updated
    assert "## Unreleased\n\n- No unreleased changes yet." in updated


def test_extract_release_notes_returns_section_body() -> None:
    changelog = """# Changelog

## Unreleased

- No unreleased changes yet.

## [2026.4.14] - 2026-04-14

### Added

- Initial release.
"""

    notes = extract_release_notes(changelog, "2026.4.14")

    assert notes == "### Added\n\n- Initial release.\n"
