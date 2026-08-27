# PPTrans v2 architecture

PPTrans v2 translates text in editable `.pptx` presentations by patching the original OOXML package. It does not recreate slides from a simplified object model. The central design goal is a verifiable, fail-closed transaction whose authorized changes are a known set of DrawingML text-node values.

This document describes the current `2.0.0a1` implementation. The separate review modules are a foundation and are not yet an end-to-end CLI feature.

## System boundaries

```text
untrusted .pptx
      |
      v
inspect + source guards -----> immutable DeckPlan
                                   |
                          local memory lookup
                                   |
                                   v
                         exact-ID provider request
                                   |
                         strict response validation
                                   |
                                   v
                              PatchSet
                                   |
source .pptx ------------> staged package copy
                                   |
                         text-node-only patch
                                   |
                            post-write verify
                                   |
                       fsync + atomic publication
                                   |
                                   v
                         distinct output .pptx
```

The source presentation never becomes the output path. Cloud providers see a text-only request document, not the `.pptx` file. Translation memory is local SQLite. Optional visual rendering is a separate local boundary that invokes LibreOffice and rasterizes its PDF output.

## Component map

| Area | Responsibility |
| --- | --- |
| `domain/` | Immutable plans, locators, spans, patches, reports, limits, and errors |
| `ooxml/package.py` | Defensive ZIP/OPC access, slide-part discovery, and copy-on-write package serialization |
| `ooxml/xml.py` | Hardened XML parsing, text assignment, and structural fingerprints |
| `ooxml/inspect.py` | Slide-order traversal and immutable translation-plan construction |
| `ooxml/locate.py` | Nested shape-ID paths, table/paragraph resolution, and span extraction |
| `ports/` | Provider-neutral translator and translation-memory protocols |
| `application/translate.py` | Memory lookup, batching, exact provider-result validation, and statistics |
| `adapters/providers/` | OpenAI, Anthropic, and offline identity adapters |
| `adapters/sqlite_memory.py` | Strict local translation-cache persistence |
| `ooxml/patch.py` | Patch-set construction and planned `a:t` replacement |
| `ooxml/verify.py` | Package, structure, planned-value, and unchanged-text verification |
| `application/deck.py` | Staging, verification, fsync, cleanup, and atomic destination publication |
| `schemas/`, `review/`, `adapters/renderers/` | Strict review data, privacy/budget policy, allowlisted repair plans, and optional rendering |
| `cli.py` | `inspect`, `translate`, and `doctor` user workflows |

Dependencies point from the CLI and adapters toward application/domain contracts. Provider SDK response types do not enter the OOXML core.

## 1. Inspect without rewriting

`inspect_deck` resolves the input and computes its SHA-256 before parsing. `open_package` accepts only `.pptx`, then validates:

- member paths and required OPC parts;
- duplicate members, ZIP symbolic links, and encrypted entries;
- digital-signature parts that a translation would invalidate;
- duplicate presentation-relationship IDs, repeated slide-relationship references, and repeated slide-part references;
- member count, individual expanded size, XML-part expanded size, total expanded size, and compression ratio; and
- semantic ceilings for slide count, XML elements per inspected slide part, discovered translation units, text spans, source characters, per-unit translatable spans, per-span source characters, and accumulated diagnostics.

Inspection also reads every archive member and verifies its CRC before any provider is created. Corruption in an opaque media or embedded part therefore fails before potentially paid translation work.

The default semantic ceilings are 500 slides, 250,000 XML elements per inspected slide part, 10,000 translation units, 50,000 text spans, 5,000,000 source characters, 10,000 translatable spans per unit, 100,000 source characters per translatable span, and 10,000 diagnostics. Together with 20,000 members, 256 MiB per member, 32 MiB per XML part, 1 GiB total expansion, and a 500:1 compression ratio, they bound work before translation. Python callers may provide a reviewed `PackageLimits` policy for a trusted exception.

XML is parsed with DTD loading, external entities, and network access disabled. Slide parts are discovered through the presentation relationships in presentation order.

Inspection recursively walks slide-local shapes using `p:cNvPr/@id`. A nested `shape_id_path` is stable across sibling reordering as long as IDs and ancestry do not change. The locator also records the slide part, container type, table row/column when applicable, and paragraph index.

Each direct `a:r/a:t` becomes a translatable span when its text is nonblank. Each direct `a:fld/a:t` is included as a locked field span for context and source verification but is not sent back as a translatable target. A paragraph becomes one semantic translation unit while retaining its exact run/span boundaries. Adjacent units on the same slide provide limited before/after context.

The unit source digest covers its locator, span order, node indexes, kinds, source strings, and translatability. A deterministic unit ID derives from that digest and the plan schema. After inspection, the whole-file hash is checked again so a concurrently changed source cannot produce a valid plan.

## 2. Translate across an exact-ID boundary

`translate_plan` looks up each unit in translation memory, batches only misses, and calls the provider-neutral `Translator` protocol. The request includes languages, optional style and glossary, adjacent text context, and the ordered spans. It excludes the deck path, file hash, package parts, shape locators, media, notes, and raw XML.

Before constructing a paid-provider client, the CLI conservatively validates the complete plan against explicit provider budgets. Defaults allow 2,000 provider units, 100 logical batches, 2,000,000 source/context characters, and 5,000,000 serialized request characters across the run. Each serialized batch also has a fixed 1,000,000-character ceiling. After translation-memory lookup, `translate_plan` repeats the budget check against cache misses; SDK-internal retries are separate from PPTrans logical-call statistics.

Provider output is untrusted. Strict schemas reject unknown fields and wrong types. Application validation then requires:

- exactly the requested unit IDs in request order;
- exactly the translatable span IDs in source order for each unit;
- no missing, extra, duplicate, reordered, or locked-field target;
- nonblank strings containing only XML 1.0-valid characters and within the schema length ceiling;
- a bounded expansion ratio; and
- unchanged high-confidence URLs, email addresses, placeholders, and digit sequences.

Only a fully validated batch is added to memory. Cached rows pass the same per-unit validation before reuse, and later patch validation repeats the source and exact-ID guards.

See [PROVIDERS.md](PROVIDERS.md) for the SDK-specific adapters and complete data boundary.

## 3. Key translation memory by meaning

The local memory key is a SHA-256 of canonical JSON containing:

- a translation-contract fingerprint derived from the exact provider system instructions and strict response schema;
- source and target languages;
- provider and model;
- style and the ordered glossary, including notes;
- adjacent before/after context;
- every span's ID, kind, source text, translatability, order, and segmentation.

Changing any semantic input—including the prompt or response schema—causes a miss. Deck path, whole-file hash, and batch size are intentionally absent, so equivalent content and context can reuse a translation across decks. The SQLite row stores only the opaque key, validated translated spans, and a creation timestamp. It does not store the deck path or source metadata, but translated text remains sensitive and is not encrypted by PPTrans.

Cache opening rejects a symbolic-link leaf. On POSIX, missing parent directories request mode `0700`, a new database is exclusively created with mode `0600` (or stricter under the process umask), and the regular file is reopened without create permission before SQLite connects. Existing permissions and ACLs are preserved; Windows relies on inherited ACLs. The adapter requires `DELETE` rollback-journal mode so successful transactions do not retain WAL/SHM sidecars, while acknowledging that a plaintext rollback journal can exist during a transaction or remain after a crash. This is not encryption or an ACL audit.

## 4. Build and apply a source-guarded patch set

`build_patch_set` binds translations to the plan's file hash, unit locator, source digest, original spans, and exact ordered translated spans. Complete translation is required by default; partial patching exists only as an explicit Python API option.

Before provider construction, the CLI rejects the source as destination, non-`.pptx` output, a source/output/configuration/cache path collision, a cache or destination symbolic-link leaf, and an existing output unless overwrite is explicit. It also confirms the source hash and probes the destination directory for writability. `write_translated_deck` repeats output alias and destination checks immediately before staging and creates its temporary file in the output directory. The public low-level `apply_patch_set` and `rewrite_package` APIs also default to no-clobber, reject resolved-path and same-file aliases, and reject a symbolic-link destination even when explicit overwrite is requested.

Before patching, the source hash is checked again. Each locator is resolved against freshly parsed slide XML. PPTrans compares the current spans and source digest to the plan, then assigns only the selected existing `a:t` values. Leading or trailing whitespace adds `xml:space="preserve"` to that translated node when necessary.

No run, paragraph, shape, relationship, media, geometry, table, theme, or package member is created by the translation patcher. Every archive member is copied in original order; only explicitly targeted slide parts can receive serialized replacement XML.

## 5. Verify before publishing

Verification reopens both packages and proves:

1. the source still has the plan's SHA-256;
2. both ZIP archives pass CRC checks;
3. member names and ordering are identical;
4. every untargeted package member is byte-identical when decompressed;
5. each targeted slide has the same canonical structural fingerprint after masking `a:t` values and their `xml:space` attribute;
6. the number and kinds of text nodes are unchanged;
7. every planned span has its expected source or translated value;
8. every unplanned text node and its whitespace semantics remain unchanged;
9. no changed part falls outside the patch set.

Target slide XML is reserialized, so byte-for-byte equality is not promised for a changed slide part. The stronger relevant assertion is that its canonical structure is unchanged and only authorized text/whitespace fields differ.

After successful verification, the staged file is flushed with `fsync`. Default publication uses an atomic hard link that fails if a destination appeared after preflight, closing the no-overwrite race without exposing a partial file. Filesystems that cannot provide this primitive fail closed. With explicit overwrite permission, the verified staged file atomically replaces the destination. A failure removes the staged file; an earlier destination remains intact through inspection, translation, patching, and verification failures.

## Preservation contract

The v2 translation transaction guarantees what it checks, not universal visual equivalence:

- the source bytes are untouched;
- package inventory and order are preserved;
- unrelated package-part payloads are unchanged;
- targeted slide XML retains its masked structural fingerprint;
- only planned regular text spans may change;
- fields and unplanned text remain unchanged;
- the result is a readable ZIP package and is exercised by tests through an independent `python-pptx` reopen.

The test fixture covers mixed runs, fonts, emphasis, colors, hyperlinks, paragraph properties, line breaks, fields, merged/formatted tables, nested groups, rotation, and multiple slides. That is regression evidence for those fixtures, not proof for every PowerPoint feature or renderer. Longer translations can still overflow without changing the OOXML structure. See [LIMITATIONS.md](LIMITATIONS.md).

## Optional review foundation

The review foundation is deliberately separated from the translation transaction:

- `LibreOfficeRenderer` copies the input once into a private per-run directory, then hashes, counts, converts, and rasterizes that same snapshot. It uses an isolated LibreOffice profile, explicitly includes hidden slides in the Impress PDF export, verifies the expected whole-deck page count when available, and produces bounded PNGs through the optional PyMuPDF dependency.
- strict review schemas accept observations only; pass/fail and a weighted score are computed locally;
- privacy policies decide whether original, translated, or overlay images may be selected for upload and whether manifest text is included;
- budgets reserve requests, slides, pixels, output tokens, and repair rounds before work;
- repair plans contain only typed, bounded, allowlisted operations and must target known shape IDs.

There is currently no multimodal review-provider adapter, end-to-end review orchestrator, CLI review command, or repair executor. The renderer metadata calls LibreOffice output high-fidelity because it renders the whole deck rather than reconstructing text, but it does not claim pixel identity with Microsoft PowerPoint.

## CLI output boundary

Human-facing values such as paths, warnings, errors, and optional inspected text pass through a terminal sanitizer that renders every Unicode `Cc` control character as visible `\uXXXX` text; only intentional newlines in inspected text are retained. Machine modes write compact `ensure_ascii=True` JSON directly to standard output, without Rich markup, highlighting, or ANSI color. This keeps machine output parseable and prevents untrusted deck text or paths from becoming terminal-control sequences; it is not a general log-sanitization guarantee for external callers.

## Extension rules

A new translation provider should implement `Translator`, return provider-neutral immutable values, and satisfy the exact-ID contract with offline mocked tests. A new renderer should implement `SlideRenderer`, report availability without side effects, validate inputs and outputs, and enforce resource ceilings. A future repair executor must map each allowlisted operation to deterministic local code; it must never accept executable code or arbitrary property paths from a model.

Refer to [CONTRIBUTING.md](../CONTRIBUTING.md), [QUALITY_GATES.md](QUALITY_GATES.md), and [THREAT_MODEL.md](THREAT_MODEL.md) before changing one of these boundaries.
