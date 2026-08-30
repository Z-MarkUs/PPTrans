---
name: pptrans-engineering
description: Implement, debug, benchmark, and release PPTrans changes affecting PPTX inspection, source-guarded OOXML text patching, preservation verification, provider adapters, review workflows, documentation claims, or package distribution. Use for engineering work in this repository; do not use merely to translate a deck with the installed CLI.
---

# PPTrans engineering

Build changes that keep editable PowerPoint output reliable, provider behavior explicit, and project claims supported by reproducible evidence.

## Route the work

- For OOXML inspection, stable locators, text patching, preservation verification, tables, groups, rendering, or provider boundaries, read [architecture](references/architecture.md).
- For tests, fixture design, benchmarks, package checks, or completion evidence, read [verification](references/verification.md).
- For versioning, publishing, release notes, provenance, or GitHub release preparation, read [release guidance](references/release.md).

Read only the references relevant to the current request. Inspect the current code before relying on a reference when implementation details may have changed.

## Preserve the important invariants

- Treat `.pptx` as an OPC/OOXML package, not a collection of strings. Patch addressed text nodes in a staged copy; preserve member names and ordering, unrelated member bytes, and the structural fingerprint of targeted XML parts.
- Address paragraphs through source-guarded locators and span IDs. Preserve paragraph/run structure and reject stale, incomplete, duplicate, or unknown translation targets.
- Keep layout repairs separate from translation patches. Apply only typed, allowlisted repairs whose targets and bounds have been validated.
- Never overwrite the input deck. Keep intermediate and failure artifacts scoped to a temporary directory and clean them predictably.
- Treat model output as untrusted data. Parse it against an explicit schema and never execute model-generated Python or shell code.
- Keep the default suite offline. Use deterministic providers and self-authored fixtures; run paid or data-exporting tests only with explicit authorization.
- Fail clearly on unsupported formats, provider capabilities, malformed responses, or partial processing. Preserve actionable diagnostics for recognized unsupported content; use and test `--fail-on-warnings` when an automated workflow requires zero emitted warnings, without claiming that warning-free inspection is exhaustive.
- Do not claim formatting preservation, vision review, model compatibility, speed, quality, or cost without current evidence covering the claim.

## Complete the change

Run focused checks while iterating and the applicable repository gates before finishing. Report what passed, what was skipped, and why. A release or external repository mutation still requires explicit user authorization and the provenance gate in `NOTICE.md` to be resolved.
