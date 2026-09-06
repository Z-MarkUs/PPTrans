# Release and attribution guidance

## Authorization and release gate

Preparing a release is not authorization to publish it. Before a tag, release, or index upload, require an exact version/tag, target commit, registry or release channel, and artifact set; for any other live mutation, require the exact target and requested change. Authorization is action-specific: permission to publish does not by itself authorize secret revocation, workflow changes, repository-rule changes, tag deletion, or overwriting an existing release. Do not push tags, create a GitHub release, upload to an index, or change live repository settings without the corresponding explicit user request.

Read `NOTICE.md` and `LICENSE` before public source or release work. Preserve the transparent upstream attribution and applicable license notices, and do not describe the project as wholly original or clean-room. This attribution requirement does not block a normal public source branch; source publication remains distinct from a versioned tag, GitHub release, or package-index upload.

CI deliberately rejects the package gate for every versioned tag created from the guarded tree while `scripts/check_release_policy.py` records prerelease status, missing separate authorization, an incomplete checklist, or unfinished live-host workflow migration. This is a reactive artifact safeguard, not a restriction on publishing a normal source branch or control over Git ref creation. Before enabling a versioned-release workflow, require repository rules that restrict version-tag creation; a tag cut from an older revision can carry an older workflow and bypass a newly added CI step. Do not bypass or weaken either control. Record every satisfied release prerequisite in a reviewed update to the policy script, tests, and release guidance before proposing a tag or release workflow.

The 2026-08-31 read-only audit of `origin/main` found legacy `release: created` workflows that can publish to PyPI with a stored secret and build application artifacts. Treat those historical workflows and any credential they reference as an external versioned-release blocker. Before any tag, GitHub release, or package-index publication, obtain separate authority for the needed host-side actions or hand them off explicitly: disable or revoke the legacy path, restrict tag and release creation, and verify the deployed default branch contains only the reviewed workflows. A source-tree edit cannot prove those controls are active, and source-branch publication does not authorize changing them.

## Version and artifact discipline

Use one authoritative package version and derive runtime reporting from it. Before tagging, confirm the changelog, package metadata, installed version, tag, and release title agree. Disposable local builds used only for package validation are allowed during prerelease development under the controls in `verification.md`; they are not releasable artifacts. Build artifacts intended for upload or attachment only from the tagged commit after the offline, integration, package, documentation, authorization, and live-host workflow gates pass.

Prefer trusted publishing and short-lived credentials. Never place tokens in files, commands that print them, build logs, release notes, or artifacts. Attach only platform binaries that were actually smoke-tested; otherwise publish the verified wheel and source distribution without implying unsupported installers exist.

Treat tags and package versions as immutable coordinates. Record the reviewed commit and artifact checksums before the first mutation; create and read back the remote tag before publishing; query the package index for authoritative success before creating the matching GitHub release. Before every irreversible call, check whether the coordinate already exists. If a response is ambiguous, do not retry blindly: query the destination and stop for human confirmation when success cannot be established. If only part of a release succeeds, preserve the successful immutable objects, report the split state, and recover without moving a tag, replacing an artifact, or reusing a published version for different bytes.

## Release evidence

Release notes should state what changed, compatibility or migration impact, tested Python and platform scope, known limitations, and links to raw benchmark results. Include checksums and a software bill of materials when the release process supports them. Keep provider-dependent measurements separate and record the provider, model, date, fixture revision, and environment.

## Repository presentation

Use a factual GitHub description and topics. A README badge must point to the workflow that proves its claim. Screenshots and demo decks must be self-authored or have documented redistribution rights. Avoid star counts, static “passing” badges, unmeasured superlatives, and model-specific claims that will become stale.
