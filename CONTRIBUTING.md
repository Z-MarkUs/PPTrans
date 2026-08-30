# Contributing to PPTrans

PPTrans v2 is being rebuilt around a narrow promise: translate editable `.pptx` text while changing as little of the OOXML package as possible. Contributions are welcome when they preserve that promise and make their evidence easy to review.

Before contributing, read the [provenance notice](NOTICE.md). The upstream licensing question recorded there is unresolved, so package publication and release work remain gated even when the code is technically ready.

## Set up a development environment

Use a supported CPython release from 3.10 through 3.13 in a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,review]"
```

The `review` extra installs the PDF rasterizer used by the optional LibreOffice rendering foundation. LibreOffice itself is a separate system dependency. Translation and the default test suite do not require PowerPoint, LibreOffice, network access, or provider credentials. Pytest blocks in-process Python socket creation by default; this is not OS-level egress control and is not inherited by subprocesses, so subprocess tests must remain explicitly offline too.

Run a read-only environment check with:

```bash
pptrans doctor
```

## Understand the invariants first

The [architecture](docs/ARCHITECTURE.md) explains the inspection, exact-ID provider, patch, verification, and atomic-publish stages. The most important rules are:

- never overwrite the source presentation;
- treat the source deck, provider output, cached output, and rendered artifacts as untrusted data;
- patch only planned DrawingML `a:t` values;
- preserve package membership and ordering, unrelated member bytes, and the structural fingerprint of changed slide parts;
- reject stale plans, missing or invented IDs, reordered spans, malformed schemas, and partial provider results;
- never execute model-generated Python, shell commands, or expressions;
- keep visual review and bounded layout repairs separate from translation.

See the [threat model](docs/THREAT_MODEL.md) and [known limitations](docs/LIMITATIONS.md) before expanding an input, provider, renderer, or repair boundary.

## Make a focused change

Keep dependencies pointing inward:

- `domain/` contains immutable values and errors;
- `ports/` defines provider and memory protocols;
- `application/` orchestrates use cases;
- `ooxml/` owns package inspection, location, patching, and verification;
- `adapters/` integrates SDKs, SQLite, and renderers;
- `schemas/` validates untrusted structured data;
- `review/` contains provider-neutral policy and allowlisted repair plans.

Avoid broad refactors mixed with behavior changes. Do not edit the generated `.claude/skills/pptrans-engineering/` copy directly; edit the canonical `.agents/skills/pptrans-engineering/` skill and run the synchronization command below.

## Add evidence with the code

Tests should be offline, deterministic, and safe to publish.

- Build presentation fixtures in the test at runtime from author-owned content.
- Use fake or injected provider clients; never spend credits in the default suite.
- Assert both the intended translation and the preservation contract.
- Include failure tests for malformed, stale, partial, duplicated, and reordered data.
- For renderer work, test command construction, timeouts, resource ceilings, environment redaction, and invalid output.
- Do not commit customer decks, provider responses, API keys, local translation-memory databases, or generated review images.

A live provider or renderer smoke test is supplementary evidence, not a replacement for deterministic tests. It requires explicit authorization, synthetic content, and a separate report of the provider/model or renderer version used.

## Run the applicable quality gates

For a complete code change, run:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src/pptrans
python -m pytest -q
python -m bandit -q -r src/pptrans
python scripts/sync_agent_skills.py --check
python scripts/validate_agent_skills.py
```

Use the full [quality-gate checklist](docs/QUALITY_GATES.md) for OOXML, provider, packaging, benchmark, or release changes. A focused test is useful while iterating, but report the complete commands actually run and any checks skipped.

## Documentation and performance claims

Document current behavior, not planned behavior. In particular, do not describe the review foundation as an end-to-end vision-review feature until a reviewed provider adapter, orchestration path, and repair executor exist and are tested together.

Every speed, cost, quality, compatibility, or preservation claim needs committed evidence identifying the commit, fixture, environment, and command. Do not infer universal PowerPoint compatibility from a synthetic fixture or a successful `python-pptx` reopen.

Update [CHANGELOG.md](CHANGELOG.md) under the Unreleased version when a user-visible behavior changes. New limitations belong in [docs/LIMITATIONS.md](docs/LIMITATIONS.md); new trust boundaries or mitigations belong in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Submit a reviewable pull request

Include:

- the problem and intended behavior;
- the preservation or security invariants affected;
- tests and commands run, with results;
- any skipped live checks and why;
- documentation changes;
- migration or compatibility impact.

Use [SECURITY.md](SECURITY.md) for vulnerabilities rather than opening a public issue with exploit details. Releases remain subject to the provenance gate in [NOTICE.md](NOTICE.md).
