# Changelog

All notable changes to `sulis-workflows`. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: [SemVer](https://semver.org/). A release is a `vX.Y.Z` git tag.

## [Unreleased]

### Added
- Repo scaffold + release process (trunk-based; release-on-tag CI). Per DR-040.

## [0.0.0] — 2026-06-16
- Initial scaffold: package skeleton (`sulis_workflows`), CI, release pipeline, README.
  The engine extraction from the platform (`apps/api/sulis/shared/workflows`) follows;
  `v0.1.0` will land the pure core (domain + ports + compiler).
