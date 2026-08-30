# Offline operation

Use this workflow for environment diagnosis, read-only inspection, and a no-network identity transaction. None of these commands require a provider credential.

## Diagnose without a network call

From the environment where PPTrans is installed, run:

```bash
pptrans doctor
```

Required dependency failures block the operation. Optional fixture-authoring or rendering warnings do not make the formatting-safe core unavailable. `doctor` checks local presence only; it does not contact a provider.

## Inspect privately

Start with deck-text-free JSON and a conservative warning policy:

```bash
pptrans inspect "deck.pptx" --source en --target fr --json --fail-on-warnings
```

The result may include paths, hashes, counts, and diagnostics, but deck text is omitted unless `--show-text` is supplied. Do not add that option merely for debugging. Exit status 1 with `--fail-on-warnings` means recognized unsupported content was reported; it does not mean the source changed.

Inspection currently targets editable slide and table text. Opaque or unsupported material can remain preserved without producing a diagnostic, so review known limitations before promising content coverage.

## Prove the transaction offline

The identity transaction does not change text or contact a provider, but it does invoke the `translate` command and write a distinct PPTX. A request for inspection or a read-only check does not authorize that output. When the user says “do not translate” while asking to test the full pipeline, explain this distinction and confirm that a text-identical output may be created before proceeding.

Use an explicit new destination and disable plaintext translation memory:

```bash
pptrans translate "deck.pptx" --source en --target en --provider identity --no-memory --fail-on-warnings --output "deck.identity.pptx" --json
```

Choose the same source and target language because identity returns each source span unchanged. A successful result proves the current deck passed inspection, exact-ID patch construction, package verification, and atomic publication. It does not establish translation quality, visual fit, or cloud-adapter readiness.

If the destination already exists, choose a new name. Use `--overwrite` only when the user explicitly requested replacement of that exact output. On any failure, confirm the source still exists and do not describe a partial or absent output as successful.

## Handoff

Record the command scope, output path, source/output hashes reported by PPTrans, verified patch/span counts, warnings, and whether a native presentation application was used for review. Do not infer PowerPoint pixel identity from OOXML verification or a different office renderer.
