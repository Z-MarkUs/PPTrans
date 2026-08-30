# Verification workflow

## During implementation

Start with the narrowest test that exercises the changed contract. Use a deterministic provider whose output is deliberately short, long, multiline, and Unicode so layout paths are exercised without network variability. Write all decks and intermediate files under pytest's `tmp_path` or another disposable system directory.

The repository-wide pytest configuration enforces the full-suite coverage floor. While iterating, bypass that aggregate measurement explicitly rather than weakening it:

```bash
python -m pytest -q --no-cov tests/path.py::test_name
```

For a preservation or layout defect, first create the smallest self-authored deck that reproduces it. Assert package membership, unchanged-member hashes, target-part structural fingerprints, locators, spans, and translated values before adding a rendered-image regression. Pixel comparisons are useful for detecting a change, but they do not identify whether translation, font substitution, or renderer drift caused it.

## Offline completion gate

Run:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src/pptrans tests/typecheck_provider_exports.py tests/test_provider_sdk_wire_contracts.py scripts/check_wheel.py scripts/rebuild_demo.py scripts/reproduce_native_demo.py
python -m pytest -q
python -m bandit -q -r src/pptrans
python scripts/check_doc_links.py
python scripts/rebuild_demo.py --check
python scripts/sync_agent_skills.py --check
python scripts/validate_agent_skills.py
pptrans inspect examples/pptrans-demo.en.pptx --source en --target en --json --fail-on-warnings
```

Pytest blocks in-process Python socket creation by default. This is not OS-level egress control and is not inherited by subprocesses, so subprocess commands must remain explicitly offline. Any authorized live-provider test is a separate invocation with an explicit network opt-in and applicable external controls. Follow `docs/QUALITY_GATES.md` for integration, packaging, benchmark, and release evidence. Do not lower a gate merely to make an unrelated change pass; distinguish an existing failure from a regression with command output and a focused test.

The documentation checker validates tracked internal destinations, fragments, exact path casing, repository boundaries, and local image evidence without requesting external URLs. Run it after any path, heading, README, demo asset, or documentation change.

For security workflow changes, pin the bytes that execute rather than trusting a wrapper action's hidden downloads. A Gitleaks update must carry the matching official archive checksum, verify it before extraction, and keep the synthetic detection control green.

## PPTX assertions

Check the properties relevant to the change, including source and output hashes, package member names and order, CRC validity, byte identity of unrelated parts, target-part structural fingerprints, stable shape-ID paths, paragraph locators, span kinds and order, and translated values. Add feature-specific assertions for relationships, geometry, tables, grouped shapes, notes, and media. For notes or other relationship-owned content, assert owner-to-part resolution, internal target containment, duplicate/shared/external-target rejection, exact eligible shape/field selection, and preservation of unselected and orphaned parts. Reopen saved decks with `python-pptx`; where the feature depends on rendered layout, use the supported office renderer and record its version.

## Provider tests

Mock SDK clients at the adapter boundary. Cover successful parsing, missing credentials, authentication failure, throttling, malformed output, and retry exhaustion. Live calls are a separate opt-in smoke test: use synthetic content, disclose cost and data transfer, and record provider, model, and date.

Exercise the adapter suite against the declared minimum OpenAI and Anthropic SDK versions as well as the normal resolved environment. Keep fixtures transport-neutral across the supported SDK range; if an adapter truly requires a newer SDK, raise and document the dependency floor instead of relying on an accidental transitive API.

Also install the base wheel in a fresh environment that contains neither paid SDK. Prove that CLI help, inspection, and identity translation work there, and that selecting a missing paid adapter fails with exact install guidance rather than an import traceback.

## Package checks

Disposable local wheel and source-distribution builds are permitted before provenance resolution when needed to validate packaging. Create them in a disposable checkout or output directory, never upload or attach them, never describe them as release candidates, and remove them after inspection. Run `python -m build --outdir <disposable-dir>`, `twine check`, and `python scripts/check_wheel.py --dist-dir <disposable-dir>`; install the wheel in a fresh temporary environment, run `python scripts/check_minimal_install.py`, `pptrans --help`, `pptrans doctor`, inspection, and an identity transaction. Verify the imported runtime version equals installed distribution metadata; only on a tag build also require the exact `v{installed-version}` tag, while the changelog and release title remain release-gate checks. Inspect wheel contents so tests, secrets, temporary decks, and provider payloads are not shipped, and confirm packages are discovered only from `src/pptrans`.
