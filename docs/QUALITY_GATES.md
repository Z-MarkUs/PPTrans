# Quality gates

These gates define the evidence required for PPTrans changes. Run the smallest relevant checks while iterating, then complete every gate affected by the change. A green command is evidence only for behavior it actually exercises.

## 1. Offline change gate

Run for every code or test change:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python scripts/sync_agent_skills.py --check
python scripts/validate_agent_skills.py
```

Default tests must use deterministic fake providers and temporary directories. They must not require network access, provider credentials, Microsoft PowerPoint, or private presentations.

## 2. PPTX integration gate

Changes to OOXML inspection, locator resolution, text patching, preservation verification, layout repairs, reviews, or rendering require self-authored fixture decks covering the affected structures. Verify, as applicable:

- expected text was translated exactly once;
- slide order and shape order remain stable;
- shape geometry and rotation remain unchanged unless an asserted fitting rule changes them;
- paragraph and run boundaries, bullets, indentation, hyperlinks, colors, emphasis, and alignment survive;
- tables, grouped shapes, media relationships, notes, and unsupported OOXML parts are preserved;
- the output reopens with `python-pptx` and can be rendered by the supported office renderer;
- partial failures do not overwrite the source or leave a false-success output.

A visual golden-image comparison detects regression against a known output; it does not by itself prove translation accuracy or universal formatting preservation.

## 3. Provider gate

Provider adapters require contract tests with mocked SDK responses for success, authentication failure, rate limiting, malformed responses, and retry boundaries. A live smoke test is optional during ordinary development and requires explicit authorization because it sends content externally and may incur cost.

Budget tests must cover the 2,000-unit, 100-logical-call, 2,000,000-source/context-character, 5,000,000-total-serialized-character defaults and the fixed 1,000,000-character per-request ceiling. Routing tests must prove that built-in clients pin official endpoints, reject ambient SDK endpoint/header variables, and set `trust_env=False`; deliberately injected clients are a separate caller-owned boundary.

When a live test is authorized, use a synthetic deck, record the provider and model identifier, avoid printing credentials or request bodies, and report the test separately from the offline suite.

## 4. Package gate

Before a release candidate:

```bash
python -m build
python -m twine check dist/*
python scripts/check_wheel.py
```

Install the wheel in a fresh temporary virtual environment, run `pptrans --help`, import `pptrans`, and confirm `pptrans.__version__` matches the intended tag. Confirm the wheel discovers packages only from `src` and contains the expected `pptrans` namespace without a legacy top-level package. Confirm the source distribution contains every fixture needed by its included tests, while the wheel contains no presentation fixture or private artifact. The version must have one authoritative source; duplicate declarations must be generated or tested for equality.

Do not advertise standalone binaries unless each advertised platform artifact was built, installed or launched, and smoke-tested on that platform.

## 5. Documentation and benchmark gate

Every README benchmark metric must come from a committed raw result that records the commit SHA, fixture hash/revision, Python version, operating system, and complete command. Record provider/model, cold versus warm translation-memory state, token usage, and renderer version whenever those systems participate. Separate deterministic OOXML-core results from provider-dependent translation quality, latency, cost, and visual-render results.

Remove or label claims whose evidence is absent, stale, model-specific, or narrower than the wording. Static “passing” badges are not evidence; badges must resolve to the workflow that runs the relevant gate.

The public demo has its own source and QA record in [DEMO.md](DEMO.md). A replacement must remain synthetic, be built into a disposable path, have metadata normalized, preserve the asserted slide/unit/span counts, pass the offline identity transaction and independent reopen, and receive visual review of every generated slide plus layout output. A rendered preview is presentation evidence only; it does not establish PowerPoint pixel identity or translation quality.

The current narrow result and method are committed under [`benchmarks/`](../benchmarks/). Regenerate into a new no-clobber result path from a clean tree; never overwrite old evidence or broaden the claim beyond the systems actually measured.

## 6. Release gate

A release requires all applicable gates above, a clean versioned changelog entry, synchronized package/tag versions, verified artifacts, and no unresolved secret-scanning findings. `NOTICE.md` currently records unresolved upstream licensing; do not publish another package or release until written permission or a compatible upstream license is documented.
