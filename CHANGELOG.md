# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- No unreleased changes yet.

## [2026.4.23] - 2026-04-23

- No user-facing changes were recorded for this release.

## [2026.4.15] - 2026-04-15

### Added

- Added the reproducible `promptcrab-benchmark` runner with built-in hard cases, public dataset sampling, shared token counting, judge panels, confidence intervals, and before/after gate token-reduction summaries.
- Added `opencode_cli` backend support for provider/model routes such as `minimax-coding-plan/MiniMax-M2.7-highspeed`.
- Added preflight prompt risk classification and conservative rewrite mode for literal-sensitive, format-sensitive, structured-data, symbol-sensitive, and verbatim prompts.

### Changed

- Updated model guidance and benchmark documentation with a 2026-04-15 directional single-judge snapshot.
- Improved judge parsing robustness by retrying malformed verifier JSON before failing a candidate.

## [2026.4.14] - 2026-04-14

### Added

- Initial CLI packaging, backend integration, verification pipeline, and release automation.
