# Release and provenance guidance

## Authorization and provenance gate

Preparing a release is not authorization to publish it. Do not push tags, create a GitHub release, upload to an index, or change live repository settings without an explicit user request.

Read `NOTICE.md` before release work. Repository history records inherited upstream source whose licensing was unresolved at the 2026-08-27 audit. Do not describe the project as wholly original, clean-room, or fully MIT-licensed, and do not publish another package or release until written permission or a compatible upstream license is documented.

CI deliberately rejects the package gate for every versioned tag created from the guarded tree while `scripts/check_release_policy.py` records unresolved provenance. This is a reactive artifact safeguard, not a restriction on Git ref creation. Before any public workflow deployment, require repository rules that restrict version-tag creation; a tag cut from an older revision can carry an older workflow and bypass a newly added CI step. Do not bypass or weaken either control. After documentary evidence clears the issue, update `NOTICE.md`, the policy script, tests, and release guidance together before proposing any tag or publication workflow.

The 2026-08-31 read-only audit of `origin/main` found legacy `release: created` workflows that can publish to PyPI with a stored secret and build application artifacts. Treat those historical workflows and any credential they reference as an external release blocker: before live repository work, disable or revoke that path, restrict tag and release creation, and verify the deployed default branch contains only the reviewed workflows. A source-tree edit cannot prove those host-side controls are active.

## Version and artifact discipline

Use one authoritative package version and derive runtime reporting from it. Before tagging, confirm the changelog, package metadata, installed version, tag, and release title agree. Disposable local builds used only for package validation are allowed before provenance resolution under the controls in `verification.md`; they are not releasable artifacts. Build artifacts intended for upload or attachment only from the tagged commit after the offline, integration, package, documentation, and provenance gates pass.

Prefer trusted publishing and short-lived credentials. Never place tokens in files, commands that print them, build logs, release notes, or artifacts. Attach only platform binaries that were actually smoke-tested; otherwise publish the verified wheel and source distribution without implying unsupported installers exist.

## Release evidence

Release notes should state what changed, compatibility or migration impact, tested Python and platform scope, known limitations, and links to raw benchmark results. Include checksums and a software bill of materials when the release process supports them. Keep provider-dependent measurements separate and record the provider, model, date, fixture revision, and environment.

## Repository presentation

Use a factual GitHub description and topics. A README badge must point to the workflow that proves its claim. Screenshots and demo decks must be self-authored or have documented redistribution rights. Avoid star counts, static “passing” badges, unmeasured superlatives, and model-specific claims that will become stale.
