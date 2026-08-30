---
name: pptrans-operator
description: Safely diagnose, inspect, and translate local editable PPTX decks with the PPTrans CLI while protecting the source, credentials, confidential text, and provider spend. Use for operating PPTrans on a deck; use pptrans-engineering instead for code changes, benchmarks, or releases.
---

# PPTrans operator

Operate PPTrans with an explicit data boundary, a distinct output, and evidence that the transaction completed safely.

## Route the operation

- For environment checks, deck-text-free inspection, warning handling, or the offline identity transaction, read [offline operation](references/offline-operation.md).
- Before any OpenAI or Anthropic translation, read [provider operation](references/provider-operation.md).
- For implementation, debugging, tests, benchmarks, documentation claims, or releases, use the `pptrans-engineering` skill instead (`$pptrans-engineering` in Codex; `/pptrans-engineering` in Claude Code).

Read only the reference needed for the current request. Check `pptrans --help` or the relevant subcommand help before relying on an example when the installed version may differ.

## Establish the boundary

- Accept only an editable `.pptx`. Stop on `.ppt`, `.pptm`, `.ppsx`, `.potx`, or an ambiguous source path rather than converting implicitly.
- Identify the source and target languages. Keep the source immutable and choose a distinct `.pptx` output. Do not add `--overwrite` unless the user explicitly chose the exact existing destination to replace; never target the source.
- Prefer `inspect` without `--show-text`. It is offline and omits deck text by default, but still reports source path, hash, count, and diagnostic metadata. Include deck text in terminal or JSON output only when the user requests it and that disclosure is appropriate.
- Treat emitted warnings as recognized unsupported-content signals, not a complete feature inventory. Use `--fail-on-warnings` for automated or conservative runs, and never claim that a warning-free deck is visually correct.
- Use the `identity` provider only to prove the local patch, verification, and publication path. It does not translate text or test a cloud provider.
- An identity transaction still writes a distinct PPTX. If the user asks for a read-only check or says not to translate, explain that boundary and obtain permission for the text-identical output before using `translate --provider identity`; otherwise stop after inspection.

## Protect data and spend

- A request to inspect, diagnose, or test a deck is not authorization to send its text to a cloud provider. Before a paid call, require an explicitly selected provider and exact model, and make the selected-text export clear.
- Use only an exported credential or a user-selected `--env-file`. Never search for dotenv files, print a key, place a key on the command line, or copy one into logs.
- Add `--no-memory` by default for sensitive or one-off work. The optional SQLite translation memory retains translated text locally without encryption; use it only when the user accepts that persistence and its exact path is safe.
- Before a paid call, use `translate --dry-run` to obtain a deck-text-free, zero-memory-hit workload upper bound without loading credentials, a provider SDK, translation memory, an output path, or making a provider/API request. A successful preview still discloses the source hash, counts, and diagnostics locally; validation errors may identify a user-selected failing path but must not echo glossary terms.
- Keep provider ceilings explicit and do not raise them merely to make a run proceed. They bound units, logical calls, and characters—not tokens, currency, latency, or translation quality.

## Finish with evidence

Report the source and output paths, provider and model, verification result, emitted warnings, and any checks skipped. A successful structural transaction still requires opening the result in the target presentation application to review wrapping, clipping, fonts, language shaping, and translation quality.
