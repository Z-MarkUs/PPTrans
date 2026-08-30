# PPTrans

**Translate editable PowerPoint decks by changing only the intended text nodes—then verify the package before publishing the output.**

[简体中文](README.zh-CN.md)

**Job-application attachment:** the [one-page PPTrans engineering case study](output/pdf/PPTrans-Engineering-Case-Study.pdf) compresses the role, architecture, visual proof, measured evidence, and limitations into a recruiter-ready A4 PDF. It is explicitly labeled as an unreleased, non-public local v2 showcase, contains no link to the legacy public `main` branch, and is reproducible from its [scoped claim ledger](docs/portfolio/pptrans-engineering-case-study.json). The [case-study guide](docs/portfolio/README.md) provides evaluator links and the exact clean setup and rebuild commands.

## 60-second overview

- **Role — Hehan Zhao:** maintains PPTrans and led v2's product direction, safety bar, and end-to-end re-architecture across defensive OOXML intake, strict provider contracts, transactional publication, testing, CI, and the showcase demo.
- **Outcome:** translates editable slide text at existing DrawingML `a:t` boundaries while retaining the surrounding package structure and formatting objects.
- **Integrity:** binds work to the source SHA-256 and stable unit/span addresses, patches a staged copy, verifies planned and untouched content, then publishes atomically.
- **Untrusted-AI boundary:** OpenAI and Anthropic results must satisfy strict schemas and exact IDs; partial, reordered, duplicated, or invented output fails closed.
- **Automation gate:** `--fail-on-warnings` can stop a run on recognized unsupported slide content before a provider is constructed or an output is published.
- **No-spend preview:** `translate --dry-run` reports a deck-text-free, zero-memory-hit provider-work upper bound without loading credentials, an SDK, translation memory, an output path, or making a provider/API request.
- **Privacy and security:** defensive ZIP/XML/resource limits; only selected text and context reach the explicitly chosen provider—not the deck binary, media, or raw XML.
- **Evidence:** 541 passing tests, 92.12% combined branch-aware coverage in the latest local audit, 9,346 generated property examples, cross-platform CI configuration, packaging and documentation-integrity gates, and security scanning.
- **Runnable proof:** a synthetic 3-slide / 41-unit / 45-span demo, a real changed-text zh-CN output, and scoped LibreOffice acceptance evidence.

### Before / after: the text really changes

| English source | Curated Simplified Chinese output |
| --- | --- |
| ![Native LibreOffice render of the English demo cover: “Translate PowerPoint. Preserve the PowerPoint.”](docs/assets/pptrans-demo-libreoffice-en-slide-01.png) | ![Native LibreOffice render of the Simplified Chinese demo cover: “翻译 PowerPoint。保留 PowerPoint 结构。” with the same layout](docs/assets/pptrans-demo-libreoffice-zh-CN-slide-01.png) |

Download the [English source deck](examples/pptrans-demo.en.pptx) and [verified zh-CN output](examples/pptrans-demo.zh-CN.pptx), inspect the English deck's [canonical OOXML source](examples/pptrans-demo.source/manifest.json), or run its standard-library-only [exact rebuild](scripts/rebuild_demo.py). The images above are exact native LibreOffice 26.8.0.3 renders, not authoring previews. The cover deliberately labels v2 as an unreleased local showcase and contains no repository hyperlink, so a recruiter cannot mistake the public legacy `main` branch for this audited tree. The target strings are author-reviewed fixture data routed through the real exact-ID patch/verify/publish pipeline; this demonstrates changed OOXML and preservation behavior, not production-provider translation quality. All six native before/after images, their pinned hashes, scope, and the [local replay command](scripts/reproduce_native_demo.py) are in the [demo notes](docs/DEMO.md).

## My role and contributions

PPTrans is maintained by Hehan Zhao. For v2, I defined the product direction and safety bar and led the current end-to-end re-architecture: defensive OOXML inspection, stable-ID provider contracts, transactional patch/verify/publish behavior, deterministic tests and CI, and the showcase demo. I do not present the repository history as clean-room work; imported-upstream provenance remains documented in [NOTICE.md](NOTICE.md) and currently blocks another release.

## Version status

| Track | Status | Meaning | Recommended use |
| --- | --- | --- | --- |
| v1.1.x | Published legacy release | Earlier implementation; it does not represent the v2 integrity architecture | Historical reference only |
| v2 / `2.0.0a1` | Unreleased showcase work | Current architecture, tests, changed-text demo, and native QA | Evaluate from source; not a published package |

> [!IMPORTANT]
> `2.0.0a1` is unreleased development work. Install it from source for evaluation. Package publication and another release are blocked by the unresolved provenance/licensing issue documented in [NOTICE.md](NOTICE.md).

## Architecture: a verified text-patch transaction

```mermaid
flowchart LR
    A[Untrusted .pptx] --> B[Validate ZIP and XML]
    B --> C[Inspect slide shapes and tables]
    C --> D[Immutable DeckPlan<br/>source hash + stable IDs]
    D --> E{Local memory hit?}
    E -->|No| F[Exact-ID provider request]
    E -->|Yes| G[Validated translations]
    F --> G
    G --> H[Build source-guarded PatchSet]
    H --> I[Patch planned a:t nodes<br/>in a staged package]
    I --> J[Verify inventory, structure,<br/>planned and untouched text]
    J --> K[fsync + atomic destination publish]
```

The source remains read-only. Verification checks package inventory, unrelated member bytes, the structural fingerprint of changed slides, and every planned and untouched text node before an atomic no-clobber publish. Detailed limits and failure behavior live in the [architecture](docs/ARCHITECTURE.md) and [threat model](docs/THREAT_MODEL.md).

## What is—and is not—translated

| Presentation content | v2 behavior |
| --- | --- |
| Regular text in slide-local shapes | Translated at existing DrawingML `a:t` boundaries |
| Multiple paragraphs and styled runs | Boundaries and structure retained; text values may change |
| Text in nested group shapes | Translated through nested non-visual shape-ID paths |
| DrawingML table-cell text | Translated without rebuilding the table |
| Generated fields such as dates | Preserved and integrity-checked, but locked from translation |
| Charts and SmartArt/diagram text | Package content preserved; text not translated |
| Notes, comments, masters/layouts, alt text, embedded objects, image text | Preserved where present; not translated |
| Longer text and layout fit | No automatic font resizing, box expansion, or overflow repair |
| `.ppt`, `.pptm`, `.ppsx`, `.potx` | Rejected; the translation engine accepts validated `.pptx` only |
| Visual review and repair | Safety-oriented schemas, policies, budgets, and LibreOffice renderer exist; no end-to-end review provider, CLI workflow, or repair executor yet |

Structural preservation does not prove visual fit. A valid translation can still wrap, clip, or render differently because of text expansion, fonts, language shaping, or the viewing application. Review output in the target presentation application. The detailed boundary is in [known limitations](docs/LIMITATIONS.md).

## Five-minute source quickstart

PPTrans v2 is unreleased, and the audited v2 tree is not yet public while its provenance gate remains unresolved. These commands assume this v2 source tree is already checked out, a supported CPython 3.10–3.13 is installed, and your shell is at the repository root.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the offline core, check runtime readiness, and inspect the committed demo without exposing its text:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
pptrans doctor
pptrans inspect examples/pptrans-demo.en.pptx --source en --target en --fail-on-warnings
```

On the base install, missing `python-pptx` and LibreOffice appear as optional (`Required: no`) warnings; they are fixture-authoring and visual-review capabilities, not core runtime failures, so `doctor` still exits 0.

Inspection warnings are non-fatal by default. Here, `--fail-on-warnings` makes `inspect` return status 1 if PPTrans reports unsupported content. The same option on `translate` stops before output preflight, provider construction, translation-memory access, or publication. It does not guarantee that every unsupported PowerPoint feature is detected or prove visual fit.

Preview the complete provider workload before creating an output or loading any paid-provider dependency:

```bash
pptrans translate examples/pptrans-demo.en.pptx --source en --target zh-CN --provider openai --model "MODEL_NAME" --dry-run --fail-on-warnings --json
```

For this fixture, the preview is exactly 41 provider units in 2 logical calls, 2,799 source/context characters, 8,867 serialized request characters, and 5,903 characters in the largest zero-hit request. With zero translation-memory hits, total units, calls, and character work are conservative upper bounds; the per-call grouping describes that zero-hit plan and is recomputed and revalidated after cache lookup. These are not token, price, latency, model-availability, or translation-quality estimates. A successful preview payload emits the source hash and structural/workload counts but no source path or slide text, and it uses no credential, provider SDK, translation memory, output path, or provider/API request.

Then exercise the complete transaction offline:

```bash
pptrans translate examples/pptrans-demo.en.pptx --source en --target en --provider identity --no-memory --fail-on-warnings --output pptrans-demo.identity.pptx --json
python scripts/build_curated_demo.py examples/pptrans-demo.en.pptx pptrans-demo.curated.zh-CN.pptx
```

`identity` is a no-op provider for proving the offline transaction; its `provider_calls` value counts local adapter batches, not network calls. The second command routes a complete, author-reviewed mapping through the same orchestration and writer to prove actual changed text; its JSON lists the changed slide parts and verified span count. Choose another output name or add `--overwrite` when rerunning either command. Both paths are pinned by integration tests and scoped native records. See the [complete demo and QA notes](docs/DEMO.md).

## Translate with a provider

Run the deck-text-free `--dry-run` shown above first and review its warnings and ceilings. Only then install the adapter you intend to use, export its credential or pass an explicit `--env-file`, and choose a distinct output. PPTrans never searches for dotenv files or chooses a paid model implicitly. Dry-run rejects `--output`, `--overwrite`, `--env-file`, and `--memory` so the preview cannot silently cross into output, credential, or persistent-cache handling.

```bash
python -m pip install -e ".[openai]"
pptrans doctor --provider openai --env-file .env
pptrans translate examples/pptrans-demo.en.pptx --source en --target zh-CN --provider openai --model <explicit-model-name> --env-file .env --glossary examples/glossary.example.yaml --no-memory --fail-on-warnings --output pptrans-demo.zh-CN.pptx
```

Anthropic installs with `.[anthropic]` and uses `--provider anthropic` plus `ANTHROPIC_API_KEY`. The offline core and identity adapter import neither paid SDK. The one-off example uses `--no-memory` because the default cache is persistent plaintext SQLite; use an explicitly reviewed `--memory` path only when that retention is intended. `--style`, `--glossary`, and `--json` expose the other main controls. Paid work is preflighted against unit, call, source/context, and serialized-request ceilings. The strict warning option blocks only diagnostics PPTrans actually emits; it is not an exhaustive feature-support check. See [provider integration](docs/PROVIDERS.md) for the complete CLI, routing, and cost boundaries.

### Provider contract and privacy

| Adapter | Contract | Credential |
| --- | --- | --- |
| OpenAI | Responses API with strict JSON Schema; requests set `store=False` | `OPENAI_API_KEY` |
| Anthropic | Messages API with exactly one forced schema tool call | `ANTHROPIC_API_KEY` |
| Identity | Offline, deterministic pass-through for pipeline verification | None |

The provider request includes selected slide text, adjacent paragraph context, source/target language, optional style, and glossary terms. It excludes the `.pptx` binary, file path, raw XML, formatting, images, notes, relationships, and embedded files. Selected text is still a data export: obtain authorization and review the provider's retention terms before processing sensitive content.

The default translation memory is local, persistent, and **unencrypted** SQLite. Use `--no-memory` for sensitive work. Cache identity, permissions, journaling, endpoint pinning, proxy behavior, and caller-injected client responsibilities are documented in [provider integration](docs/PROVIDERS.md) and [security policy](SECURITY.md).

## Evidence, not slogans

The repository's quality claims are scoped to checks that actually run:

- [Core, safety, and property tests](tests/) cover rich OOXML fixtures, malicious packages, stale sources, unplanned changes, and 9,346 generated Unicode/order/path/mutation examples.
- [Provider adapter tests](tests/test_provider_adapters.py) exercise strict schemas, safe error mapping, configuration, and failure boundaries with injected clients. Separate [wire-contract tests](tests/test_provider_sdk_wire_contracts.py) pass through the real OpenAI and Anthropic SDK serializers and response models using in-memory HTTP transports—at current and declared-minimum SDK versions, with no socket or provider call.
- [CLI and application tests](tests/test_cli_v2.py) bind provider-budget validation to the same deterministic estimator used by `--dry-run`, assert exact per-call arithmetic, replace credential/provider-SDK-import/socket/memory/output boundaries with failing sentinels, exercise warning and budget failures, and prove that duplicate glossary errors redact private terms.
- [Review-foundation tests](tests/test_security_review_foundation.py) scan the v2 package for dynamic execution calls and test renderer/image safety boundaries.
- [Demo and repository-tool tests](tests/) reconstruct the English deck from 29 hash-pinned OOXML members, rebuild the curated target byte for byte, pin both builders and the native replay script, enforce exact changed members and ZIP fields, and bind every native PNG to the current [exact-rebuild acceptance record](docs/qa/2026-08-31-exact-rebuild.json). The [native replay script](scripts/reproduce_native_demo.py) rebuilds the identity output and all nine recorded renders with the exact LibreOffice build; ordinary CI verifies committed evidence without requiring LibreOffice.
- [CI and security workflows](.github/workflows/) configure linting, strict typing, coverage, documentation integrity, packaging, bounded multi-OS tests, an isolated weekly audit of all dependency sets, CodeQL, and full-history secret scanning with SHA-pinned actions plus a checksum-pinned scanner archive. Version-tag package gates fail closed while provenance is unresolved; repository tag rules remain a required live-host control.

The configured combined branch-aware coverage floor is visible in [pyproject.toml](pyproject.toml). A successful workflow is evidence for its exact workflow and commit only; it is not proof of universal formatting preservation or translation quality. Public badges will be restored only after the audited v2 workflows are published and pass on the public repository.

### Benchmark status

On Windows 11 with Python 3.12.13, the committed synthetic deck completed the deterministic `inspect → identity orchestration → patch → verify` core in a **58.770 ms median** and **60.972 ms p95** over 30 measured iterations after 3 warmups. The run came from clean commit `7cb4a1f`, used the current exact-rebuild 87,226-byte fixture with 3 slides / 41 units / 45 spans, and records its full SHA, environment, normalized reproduction command, every measured sample, and recomputable summaries in the [raw benchmark result](benchmarks/results/2026-08-31-honest-showcase-ooxml-windows-python312.json).

This is a narrow local core benchmark, not a provider, network, translation-memory, LibreOffice, rendering, cost, or translation-quality result, and it does not establish maximum practical deck size or cross-machine performance. See the [benchmark method](benchmarks/README.md) and [quality gates](docs/QUALITY_GATES.md).

## Optional review foundation

Installing `.[review]` adds a bounded LibreOffice → PDF → PNG renderer plus typed review/repair schemas and budgets. Renderer cleanup is a publication barrier: source snapshots, PDF, profile, and rasters must be retired before final images appear, and failures roll back owned outputs. This is foundation code—not a multimodal review workflow, PowerPoint-equivalence guarantee, or repair executor. See the [architecture](docs/ARCHITECTURE.md).

## Built for Codex and Claude Code

PPTrans includes repository-native guidance so coding agents inherit the same invariants as human contributors:

- [AGENTS.md](AGENTS.md) defines architecture, safety, testing, and Git rules.
- [.agents/skills/pptrans-operator/](.agents/skills/pptrans-operator/) is the canonical deck-operation skill for private inspection, no-side-effect preview, identity verification, and carefully authorized provider runs. Invoke it in Codex as `$pptrans-operator`; its byte-identical Claude Code mirror is invoked as `/pptrans-operator`.
- [.agents/skills/pptrans-engineering/](.agents/skills/pptrans-engineering/) is the separate implementation, debugging, benchmark, documentation-claim, and release skill. Invoke it in Codex as `$pptrans-engineering`; its byte-identical Claude Code mirror is invoked as `/pptrans-engineering`.
- [CLAUDE.md](CLAUDE.md) imports the repository guidance, while inventory-aware sync and validation scripts prevent either pair of skill copies from drifting or disappearing from the source distribution.

The operator skill treats inspection as read-only, requires a dry run before paid work, and makes credential, confidentiality, persistence, overwrite, and retry boundaries explicit. The engineering skill routes OOXML, verification, provider, benchmark, and release work to focused references and explicitly forbids unsupported claims or model-generated code execution.

## Project map

```text
src/pptrans/
├── domain/              immutable plans, locators, spans, patches, reports
├── ooxml/               safe package inspection, location, patching, verification
├── ports/               provider and translation-memory protocols
├── application/         translation and deck transaction orchestration
├── adapters/
│   ├── providers/       OpenAI, Anthropic, offline identity
│   ├── renderers/       optional LibreOffice/PDF/PNG foundation
│   └── sqlite_memory.py local semantic translation cache
├── schemas/             strict untrusted translation/review payloads
├── review/              budgets, privacy policy, allowlisted repair plans
└── cli.py               inspect, provider preview, translate, doctor
```

## Engineering documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Providers and data boundary](docs/PROVIDERS.md)
- [Known limitations](docs/LIMITATIONS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Security policy](SECURITY.md)
- [Quality gates](docs/QUALITY_GATES.md)
- [Showcase demo source and QA](docs/DEMO.md)
- [Contributing](CONTRIBUTING.md)
- [Unreleased changelog](CHANGELOG.md)
- [Provenance and licensing notice](NOTICE.md)

## Contributing and release status

Contributions should use synthetic fixtures, deterministic provider doubles, and the applicable [quality gates](docs/QUALITY_GATES.md). Do not commit credentials, private presentations, provider payloads containing user data, generated customer content, or translation-memory databases.

The Git history includes imported upstream material with strong but incomplete evidence of MIT licensing: upstream asserted MIT before its first source commit and repeated that assertion in the exact snapshot imported here, but the referenced root license was absent; a full MIT text appeared later only beside a nested skill copy. The current engineering work does not erase that provenance or establish redistribution rights. Read [NOTICE.md](NOTICE.md) before reusing, packaging, or releasing this repository; it records the factual timeline and is not legal advice.
