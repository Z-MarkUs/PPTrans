# Verification workflow

## During implementation

Start with the narrowest test that exercises the changed contract. Use a deterministic provider whose output is deliberately short, long, multiline, and Unicode so layout paths are exercised without network variability. Write all decks and intermediate files under pytest's `tmp_path` or another disposable system directory.

For a preservation or layout defect, first create the smallest self-authored deck that reproduces it. Assert package membership, unchanged-member hashes, target-part structural fingerprints, locators, spans, and translated values before adding a rendered-image regression. Pixel comparisons are useful for detecting a change, but they do not identify whether translation, font substitution, or renderer drift caused it.

## Offline completion gate

Run:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python scripts/sync_agent_skills.py --check
python scripts/validate_agent_skills.py
```

Follow `docs/QUALITY_GATES.md` for integration, packaging, benchmark, and release evidence. Do not lower a gate merely to make an unrelated change pass; distinguish an existing failure from a regression with command output and a focused test.

## PPTX assertions

Check the properties relevant to the change, including source and output hashes, package member names and order, CRC validity, byte identity of unrelated parts, target-part structural fingerprints, stable shape-ID paths, paragraph locators, span kinds and order, and translated values. Add feature-specific assertions for relationships, geometry, tables, grouped shapes, notes, and media. Reopen saved decks with `python-pptx`; where the feature depends on rendered layout, use the supported office renderer and record its version.

## Provider tests

Mock SDK clients at the adapter boundary. Cover successful parsing, missing credentials, authentication failure, throttling, malformed output, and retry exhaustion. Live calls are a separate opt-in smoke test: use synthetic content, disclose cost and data transfer, and record provider, model, and date.

## Package checks

Build both wheel and source distribution, run `twine check`, install the wheel in a fresh temporary environment, and run `pptrans --help`. Verify that package metadata, `pptrans.__version__`, tag, changelog, and release title agree. Inspect wheel contents so tests, secrets, temporary decks, and provider payloads are not shipped, and confirm packages are discovered only from `src/pptrans`.
