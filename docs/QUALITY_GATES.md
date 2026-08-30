# Quality gates

These gates define the evidence required for PPTrans changes. Run the smallest relevant checks while iterating, then complete every gate affected by the change. A green command is evidence only for behavior it actually exercises.

The default pytest configuration enforces repository-wide coverage. For a focused iteration run, retain the test behavior while disabling only that aggregate measurement, for example `python -m pytest -q --no-cov tests/path.py::test_name`; restore the full command for completion.

## 1. Offline change gate

Run for every code or test change:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src/pptrans
python -m pytest -q
python -m bandit -q -r src/pptrans
python scripts/sync_agent_skills.py --check
python scripts/validate_agent_skills.py
pptrans inspect examples/pptrans-demo.en.pptx --source en --target en --json --fail-on-warnings
```

Default tests must use deterministic fake providers and temporary directories. Pytest blocks in-process Python socket creation by default. This is not OS-level egress control and is not inherited by subprocesses, so subprocess fixtures and commands must be kept explicitly offline too. Tests must not require provider credentials, Microsoft PowerPoint, or private presentations. A live test must be a separate, explicitly authorized invocation that deliberately overrides the in-process socket block and any applicable external egress controls.

The supported CPython range is 3.10 through 3.13. CI exercises both endpoints on Linux, macOS, and Windows, plus Python 3.11 on Linux; do not broaden the compatibility claim beyond that configured range.

The provider-adapter suite also runs in an isolated CI job with the declared minimum OpenAI and Anthropic SDK versions. New adapter code must remain compatible with those lower bounds or deliberately raise and document the dependency floor.

Property tests must disable the persistent Hypothesis example database, use deterministic generation, and remove deadlines that would turn machine speed into a test outcome. Keep example budgets explicit so README evidence can be recomputed from the test source.

## 2. PPTX integration gate

Changes to OOXML inspection, locator resolution, text patching, preservation verification, layout repairs, reviews, or rendering require self-authored fixture decks covering the affected structures. Verify, as applicable:

- expected text was translated exactly once;
- slide order and shape order remain stable;
- shape geometry and rotation remain unchanged unless an asserted fitting rule changes them;
- paragraph and run boundaries, bullets, indentation, hyperlinks, colors, emphasis, and alignment survive;
- tables, grouped shapes, media relationships, notes, and unsupported OOXML parts are preserved;
- the output reopens with `python-pptx` and can be rendered by the supported office renderer;
- partial failures do not overwrite the source or leave a false-success output.

Renderer changes must additionally prove that the private source/PDF/profile/raster workspace is absent before the first final image is published, transient cleanup races are retried within a fixed bound, persistent cleanup failure publishes nothing, publication failure rolls back only owned links, and every successful or recoverable-failure path leaves no renderer staging directory. When a compatible office runtime is available, open and rasterize every slide from a synthetic source and its offline identity output, compare every render pair, inspect every slide, run the padded-canvas overflow check, and commit a scoped environment-and-hash record rather than generated working images.

A visual golden-image comparison detects regression against a known output; it does not by itself prove translation accuracy or universal formatting preservation.

## 3. Provider gate

Provider adapters require contract tests with mocked SDK responses for success, authentication failure, rate limiting, malformed responses, and retry boundaries. A live smoke test is optional during ordinary development and requires explicit authorization because it sends content externally and may incur cost.

Budget tests must cover the 2,000-unit, 100-logical-call, 2,000,000-source/context-character, 5,000,000-total-serialized-character defaults and the fixed 1,000,000-character per-request ceiling. Routing tests must prove that built-in clients pin official endpoints, reject ambient SDK endpoint/header variables, and set `trust_env=False`; deliberately injected clients are a separate caller-owned boundary.

When a live test is authorized, use a synthetic deck, record the provider and model identifier, avoid printing credentials or request bodies, and report the test separately from the offline suite.

## 4. Package gate

Package-affecting changes may use disposable local builds before provenance resolution. Create them in a disposable checkout or output directory, inspect and install them locally, then remove them; do not upload, attach, or describe them as release-candidate artifacts. Releasable artifacts remain subject to the release gate.

After provenance passes, build a release candidate from the tagged commit. The same commands may target a disposable directory for local package validation before then:

```bash
python -m build --outdir .tmp-dist
python -m twine check .tmp-dist/*
python scripts/check_wheel.py --dist-dir .tmp-dist
```

Install the wheel in a fresh temporary virtual environment, run `pptrans --help`, import `pptrans`, and confirm its runtime version matches the installed distribution metadata. On a tag build, also require the exact repository convention `v{installed-version}`; the changelog and eventual release title remain separate release-gate checks. Confirm the wheel discovers packages only from `src` and contains the expected `pptrans` namespace without a legacy top-level package. Confirm the source distribution contains every fixture needed by its included tests, while the wheel contains no presentation fixture or private artifact. The version must have one authoritative source; duplicate declarations must be generated or tested for equality.

Do not advertise standalone binaries unless each advertised platform artifact was built, installed or launched, and smoke-tested on that platform.

## 5. Documentation and benchmark gate

Every README benchmark metric must come from a committed raw result that records the commit SHA, fixture hash/revision, Python version, operating system, and complete command. Record provider/model, cold versus warm translation-memory state, token usage, and renderer version whenever those systems participate. Separate deterministic OOXML-core results from provider-dependent translation quality, latency, cost, and visual-render results.

Remove or label claims whose evidence is absent, stale, model-specific, or narrower than the wording. Static “passing” badges are not evidence; badges must resolve to the workflow that runs the relevant gate.

Security-tool updates must pin the bytes that execute, not only a wrapper action. Keep the Gitleaks version and archive SHA-256 together in the workflow, take the hash from the matching official release checksum list, verify it before extraction, and retain a runtime-generated detection control so a broken scanner cannot silently report success.

The public demo has its own source and QA records in [DEMO.md](DEMO.md). A replacement must remain synthetic, be built into a disposable path, have metadata normalized, preserve the asserted slide/unit/span counts, pass the offline identity transaction and independent reopen, and receive visual review of every generated slide plus layout output. The curated changed-text target must also rebuild byte for byte, change only its asserted slide XML members, pass structural/text verification, render every target slide in the recorded office runtime, and run the padded-canvas harness. Record that harness's exact script, renderer, dimensions, padding, and result; a bare `"passed"` field is insufficient. A rendered preview is presentation evidence only; it does not establish PowerPoint pixel identity or translation quality.

The current narrow result and method are committed under [`benchmarks/`](../benchmarks/). Regenerate into a new no-clobber result path from a clean tree; never overwrite old evidence or broaden the claim beyond the systems actually measured.

## 6. Release gate

A release requires all applicable gates above, a clean versioned changelog entry, synchronized package/tag versions, verified artifacts, and no unresolved secret-scanning findings. `NOTICE.md` currently records unresolved upstream licensing; do not publish another package or release until written permission or a compatible upstream license is documented.
