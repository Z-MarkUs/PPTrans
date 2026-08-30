# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses semantic-version labels. PPTrans v2 has not been released.

## [2.0.0a1] - Unreleased

This alpha is active development, not a release candidate. Publication is blocked by the unresolved provenance and upstream-licensing gate in [NOTICE.md](NOTICE.md).

### Added

- A `src/pptrans` architecture with immutable deck plans, stable nested shape locators, source digests, exact text-span IDs, and typed domain errors.
- Defensive `.pptx` package validation for unsafe member paths, duplicate members, symbolic links, encryption, digital signatures, required parts, configurable expansion limits, and semantic slide/XML/unit/span/character/diagnostic ceilings.
- Recursive inspection of slide-local shape text, nested groups, and DrawingML table cells without rebuilding slide objects.
- Exact-ID translation contracts, strict Pydantic response schemas, and deterministic batch validation.
- OpenAI Responses API and Anthropic Messages API translation adapters that require an explicit model, plus an offline identity adapter for pipeline verification.
- A local SQLite translation memory keyed by semantic translation inputs and a prompt/schema-derived contract fingerprint rather than deck filename.
- Strict JSON/YAML glossary loading, CLI `inspect`, `translate`, and `doctor` commands, and machine-readable output modes.
- An opt-in `--fail-on-warnings` policy for inspection and translation, with actionable warning codes and slide/shape locations; strict translation stops before provider construction and output publication.
- Post-write verification of package inventory, unrelated member bytes, target-slide structure, planned text values, and unplanned text nodes.
- An optional LibreOffice-to-PDF-to-PNG rendering adapter with resource ceilings, explicit hidden-slide export, whole-deck page-count checks, staged image publication, and isolated-profile execution.
- Provider-neutral review schemas, deterministic score evaluation, privacy policy helpers, review budgets, and allowlisted repair-plan schemas.
- Cross-platform CI configuration, package smoke checks, dependency/security scanning, repository guidance, and Codex/Claude Code engineering skills.
- A self-authored three-slide public demo deck, committed Artifact Tool authoring source, deterministic metadata normalization, rendered QA preview, source-distribution fixture checks, a deterministic core benchmark harness, and English/Chinese recruiter-facing documentation.
- A clean-tree raw deterministic-core benchmark result with commit, fixture, environment, command, and distribution timings.
- A machine-readable Windows/LibreOffice native acceptance record for the synthetic source and byte-identical identity output, including exact tool versions, hashes, per-slide pixel comparison, visual/overflow review, and cleanup checks.
- A deterministic, author-reviewed EN → zh-CN showcase output that exercises real changed-text patching through the exact-ID pipeline, with six before/after previews and a second machine-readable LibreOffice acceptance record.
- Deterministic property-based stress tests covering XML character handling, Unicode round trips, exact provider result ordering, relationship target containment, and byte-mutated presentation input.

### Changed

- Translation now patches existing DrawingML `a:t` nodes in a staged OOXML package instead of reconstructing presentations through the PowerPoint object model.
- Provider output must include every requested unit and translatable span exactly once and in request order; partial, extra, duplicate, or reordered results fail closed.
- Output must be a distinct `.pptx`; the source can never be the destination, and an existing destination requires explicit overwrite permission.
- Model selection has no paid-provider default. OpenAI and Anthropic require an explicit model and credential.
- Translation memory is persistent, local SQLite by default, rejects symbolic-link leaves, requests private modes for newly created POSIX paths, requires `DELETE` journaling, and can be disabled with `--no-memory`.
- Provider clients pin official endpoints, reject ambient SDK routing overrides, construct default HTTP clients with `trust_env=False`, and load dotenv files only when the user selects one explicitly.
- CLI preflight now validates complete archive payload CRCs, source/destination/configuration/cache path separation, and destination writability before provider construction.
- Presentation discovery rejects duplicate relationship IDs and repeated relationship/slide-part references before provider construction.
- CLI provider preflight defaults to at most 2,000 units, 100 logical calls, 2,000,000 source/context characters, 5,000,000 serialized characters across all batches, and 1,000,000 characters per request.
- Default publication uses an atomic no-clobber path; destination replacement requires explicit overwrite permission.
- Low-level patch/rewrite APIs are no-clobber by default, reject source aliases, and refuse symbolic-link destinations even with explicit overwrite.
- Deck publication now treats private staging cleanup as a commit barrier: transient Windows unlink failures receive bounded retries, exhausted cleanup rolls back only identity-matching final links, and foreign replacements plus any residual paths are reported without deletion.
- Tests use the installed `src` package directly instead of a legacy root-path import shim.
- LibreOffice rendering now treats private-workspace cleanup as a commit barrier: validated PNGs move to separate same-filesystem staging, bounded transient-error retries retire the source/PDF/profile/raster workspace before publication, and late publication-stage cleanup failure rolls back owned final links.
- PyMuPDF discovery and loading now use its canonical `pymupdf` module name instead of the collision-prone legacy `fitz` alias.
- Engineering guidance now distinguishes focused tests from the full coverage gate, includes strict typing and security checks consistently, and separates disposable package validation from releasable artifacts; CI directly covers every classified Python minor, and the source-distribution gate requires complete mirrored agent-skill bundles.
- Supported Python is explicitly bounded to CPython 3.10 through 3.13, and the default pytest configuration blocks in-process Python socket creation; subprocess and OS-level egress remain separately controlled boundaries.
- CI now exercises the provider adapters against the declared minimum OpenAI and Anthropic SDK versions, in addition to the normally resolved dependency set.
- Package validation accepts a disposable distribution directory, smoke-tests installed-wheel runtime/metadata agreement, checks exact `v{version}` agreement on tag builds, and does not upload blocked distribution artifacts.
- The identity-demo QA record now pins its padded-canvas harness command, renderer, dimensions, padding, input hash, and rerun timestamp instead of recording only a bare pass result.

### Security

- Model output is data only. The v2 package contains no dynamic execution path for model-generated code.
- XML parsing disables DTD loading, entity resolution, and network access.
- Source hashes and structural verification prevent stale or structurally destructive patches from being published as successful output.
- Direct verification validates patch-set schema, unique unit/locator identities, ordered spans, source digests, and target-part existence, then reports only patches it actually traversed.
- LibreOffice is invoked without a shell and without likely credential-bearing environment variables; rendered images are validated and bounded.
- Rendering hashes, slide-counts, converts, and rasterizes one private per-run input snapshot, reducing local source-path replacement races.
- Renderer rollback records staged file identities, so cleanup removes only final hard links still owned by the failed transaction and preserves paths replaced by another process.
- Provider exceptions are mapped to concise PPTrans errors so request content is not copied into user-facing error messages.
- Provider text must be nonblank, stay within a bounded expansion, and preserve high-confidence URLs, emails, placeholders, and digit sequences.
- XML parts have a dedicated 32 MiB expansion ceiling, while safer archive/member/compression defaults bound opaque payload processing.
- Human-facing CLI values escape every Unicode `Cc` control character as visible `\uXXXX` text, while machine modes emit compact ASCII-escaped JSON directly without Rich styling or ANSI color.
- Post-write verification rejects altered `xml:space` semantics on changed text nodes even though whitespace attributes are masked by the structural fingerprint.
- The Anthropic adapter accepts exactly one named tool-use content block and rejects otherwise-correct output accompanied by text or another tool call; offline adapter tests cover authentication and rate-limit SDK failures without leaking response details.
- Secret-history CI downloads a fixed Gitleaks archive, verifies its pinned SHA-256 before extraction, proves the scanner detects a runtime-generated control fixture, and scans all fetched history without delegating installation to a dynamically downloading action.

### Removed from the v2 surface

- Legacy `.ppt` translation.
- The legacy root `main.py` compatibility launcher; the packaged `pptrans` entry point is authoritative.
- Implicit paid-provider model defaults.
- Legacy DeepSeek and Grok adapters pending a new adapter that satisfies the v2 exact-ID contract.
- The legacy dynamic-code repair/sandbox path.

### Known gaps before release

- The review modules are not yet wired into an end-to-end multimodal provider, CLI review command, or repair executor.
- The committed benchmark covers only local deterministic core processing; provider latency/cost, translation quality, rendering, and maximum practical deck size remain unbenchmarked.
- The licensing issue in [NOTICE.md](NOTICE.md) must be resolved before package publication or another release.

Earlier repository changes predate this structured changelog. Consult Git history and prior GitHub release notes for legacy-version history; v2 guarantees must not be projected onto those releases.
