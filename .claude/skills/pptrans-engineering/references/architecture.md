# Architecture and change boundaries

## Formatting-safe transaction

The v2 flow is:

1. `pptrans.ooxml.inspect.inspect_deck` defensively opens the OPC/ZIP package, discovers presentation-ordered slide parts, walks nested shapes and table cells, and returns an immutable `DeckPlan` containing stable paragraph locators, source spans, digests, and the input SHA-256.
2. Provider orchestration translates plan units and returns text keyed by translation-unit and span IDs. Provider output does not contain package paths or executable operations.
3. `pptrans.ooxml.patch.build_patch_set` rejects unknown, missing, duplicate, malformed, or reordered targets and produces an immutable, source-bound `PatchSet`.
4. `pptrans.application.deck.write_translated_deck` rejects the source as an output, checks the source hash, and creates a neighboring temporary `.pptx`.
5. `apply_patch_set` resolves every locator against the unchanged source, updates only validated DrawingML text nodes, checks the changed XML's structural fingerprint, and copy-writes the package while preserving member metadata and order.
6. `pptrans.ooxml.verify.verify_output` checks ZIP integrity, package member names and order, byte identity of unrelated parts, structural fingerprints of target parts, and every expected translated span.
7. Only after verification does the application service fsync and atomically replace the requested output path. Failure removes the staged file and leaves the source untouched.

## Ownership map

- `src/pptrans/domain/`: immutable data contracts, limits, and typed failures.
- `src/pptrans/ooxml/package.py`: bounded package opening, slide-part discovery, member hashing, and copy-on-write ZIP output.
- `src/pptrans/ooxml/xml.py`: hardened XML parsing, text validation, serialization, and text-insensitive structural fingerprints.
- `src/pptrans/ooxml/locate.py`: recursive shape paths, table/text-body resolution, paragraph locators, and source spans.
- `src/pptrans/ooxml/inspect.py`: source-bound deck plans and diagnostics for preserved-but-unsupported content.
- `src/pptrans/ooxml/patch.py`: exact translation validation and text-node-only mutations.
- `src/pptrans/ooxml/verify.py`: post-write preservation proof.
- `src/pptrans/application/deck.py`: staged, verified, atomic publication.
- `src/pptrans/schemas/` and `src/pptrans/review/`: strict review observations, deterministic decisions, privacy/budget controls, and typed allowlisted repairs.
- `src/pptrans/adapters/renderers/`: renderer boundaries and the LibreOffice implementation.

## Preservation model

The v2 core preserves the source package rather than constructing slides through `python-pptx`. Its contract is copy-on-write OOXML: every unrelated package member remains byte-identical, and a targeted slide part retains the same text-insensitive structure. Stable locators use the slide part plus nested non-visual shape-ID path, container, cell coordinates where applicable, and paragraph index; a flat shape index is not an acceptable address.

Translation patches modify text payloads only. Layout changes belong to a separate repair layer with typed operations, explicit bounds, target validation, and independent verification. Legacy `.ppt` is not an OOXML package and is unsupported unless a separately tested conversion boundary is introduced.

## Provider and data boundaries

CLI and provider code must depend on the `DeckPlan` and `PatchSet` contracts rather than SDK-specific objects leaking into OOXML modules. Capability checks must reflect real adapter behavior; a method name alone does not prove support.

Deck contents can be confidential. Send only the content required for the selected operation, avoid logging it by default, and document when text or rendered slides leave the machine. Review payloads must use strict schemas, privacy policy, and budget limits. Model output is untrusted data and must never become executable Python or shell code.
