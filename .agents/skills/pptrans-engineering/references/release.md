# Release and provenance guidance

## Authorization and provenance gate

Preparing a release is not authorization to publish it. Do not push tags, create a GitHub release, upload to an index, or change live repository settings without an explicit user request.

Read `NOTICE.md` before release work. Repository history records inherited upstream source whose licensing was unresolved at the 2026-08-27 audit. Do not describe the project as wholly original, clean-room, or fully MIT-licensed, and do not publish another package or release until written permission or a compatible upstream license is documented.

## Version and artifact discipline

Use one authoritative package version and derive runtime reporting from it. Before tagging, confirm the changelog, package metadata, installed version, tag, and release title agree. Build artifacts only from the tagged commit after the offline, integration, package, documentation, and provenance gates pass.

Prefer trusted publishing and short-lived credentials. Never place tokens in files, commands that print them, build logs, release notes, or artifacts. Attach only platform binaries that were actually smoke-tested; otherwise publish the verified wheel and source distribution without implying unsupported installers exist.

## Release evidence

Release notes should state what changed, compatibility or migration impact, tested Python and platform scope, known limitations, and links to raw benchmark results. Include checksums and a software bill of materials when the release process supports them. Keep provider-dependent measurements separate and record the provider, model, date, fixture revision, and environment.

## Repository presentation

Use a factual GitHub description and topics. A README badge must point to the workflow that proves its claim. Screenshots and demo decks must be self-authored or have documented redistribution rights. Avoid star counts, static “passing” badges, unmeasured superlatives, and model-specific claims that will become stale.
