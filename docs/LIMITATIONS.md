# Known limitations

PPTrans v2 deliberately supports a narrower surface than PowerPoint itself. These limits are part of the safety contract, not a promise that every well-formed presentation will translate completely.

## Supported translation surface

The current inspector translates nonblank regular DrawingML text runs found in slide-local:

- shape text bodies (`p:sp/p:txBody`);
- connector text bodies when present;
- shapes nested inside group shapes, using nested non-visual shape IDs;
- DrawingML table-cell text, including the merged/formatted table structures exercised by the synthetic tests;
- multiple paragraphs and multiple styled runs without merging or recreating those runs.

The patcher changes the existing `a:t` values only. Formatting, hyperlink relationships, line breaks, paragraph properties, shape geometry, rotations, table structure, media, themes, and other package parts are preserved rather than interpreted. The test suite exercises representative mixed runs, hyperlinks, fields, tables, groups, and multiple slides; it is not an exhaustive PowerPoint conformance suite.

## Preserved but not translated

The following content is retained in the package but is outside the current text-discovery surface:

- chart labels and other non-table graphic-frame content;
- SmartArt/diagram text and data parts;
- speaker notes and comments;
- slide-master and slide-layout text not materialized in a slide shape;
- alt text, metadata, embedded-object content, equations, and arbitrary extension XML;
- text inside images or video;
- regular text in package parts other than the ordered slide parts.

Inspection emits an `unsupported_graphic_frame` warning for a non-table graphic frame encountered on a slide. Other preserved opaque parts may not produce a warning. Always inspect the generated deck manually when complete coverage matters.

DrawingML field text (`a:fld/a:t`), such as a generated date, is included in source context and integrity checks but is intentionally locked and not returned as a translation target.

## Rejected inputs

The formatting-safe translation engine accepts only files ending in `.pptx` that pass defensive package validation.

Default safety limits reject more than 20,000 members, XML parts expanded beyond 32 MiB, individual package members beyond 256 MiB, packages expanded beyond 1 GiB, and members above a 500:1 compression ratio. Semantic ceilings also reject more than 500 slides, 250,000 XML elements in one inspected slide part, 10,000 translation units, 50,000 text spans, 5,000,000 discovered source characters, 10,000 translatable spans in one unit, 100,000 source characters in one translatable span, or 10,000 accumulated diagnostics. These are deliberate denial-of-service boundaries, not statements about what PowerPoint itself can open. Python API callers can supply a reviewed `PackageLimits` policy for a trusted exceptional deck.

- Legacy binary `.ppt` is not converted or translated.
- `.pptm`, `.ppsx`, `.potx`, and other Office variants are not accepted.
- Encrypted packages are rejected.
- Digitally signed packages are rejected because modifying slide text would invalidate the signature.
- Packages with unsafe or duplicate member names, ZIP symbolic links, missing required parts, duplicate presentation-relationship IDs, repeated slide/relationship references, invalid XML, or configured size/ratio-limit violations are rejected.

The low-level renderer has an explicit `allow_legacy_ppt` development option, but that does not make `.ppt` an end-to-end supported translation format. The normal renderer policy and v2 CLI remain `.pptx` only.

## Formatting preservation is structural, not visual-fit proof

Verification proves that package inventory, unrelated member payloads, masked slide structure, text-node count/kinds, locked text, and planned replacements meet the patch contract. It cannot prove that a longer translation fits a text box, that a font exists on the viewing machine, or that every renderer lays out the slide identically.

PPTrans v2 does not currently resize text, change margins, expand boxes, or repair overflow during translation. A syntactically and structurally valid output can still clip, wrap differently, overlap, or reflow. Review the result in the target presentation application, especially for dense slides and languages with different text expansion or shaping behavior.

Changed slide XML is serialized by lxml. Its canonical structure is checked, but the compressed member bytes are not expected to match the source when translated text changes. Untargeted package-member payloads are required to remain byte-identical.

## Translation behavior

- Language values are required to be nonblank strings, not validated against a fixed ISO registry. Actual support depends on the selected model.
- Translation quality, terminology, factual accuracy, tone, and cultural appropriateness remain model-dependent.
- Paragraph neighbors provide limited context only within the same slide; the provider does not receive the whole deck or document-level narrative.
- Span boundaries follow existing runs. Exact span preservation can constrain phrasing across heavily fragmented typography.
- Glossary instructions are sent to the provider; PPTrans does not apply a separate deterministic post-processing substitution.
- The CLI requires full provider output. Partial patching exists only as an explicit lower-level Python API option.
- Default provider ceilings are 2,000 units, 100 logical calls, 2,000,000 source/context characters, and 5,000,000 serialized request characters across all logical batches; every batch also has a fixed 1,000,000-character ceiling. These bounds are configurable CLI policy except for the per-batch ceiling, not provider token estimates or quality guarantees.
- There are no committed public benchmarks yet for speed, cost, translation quality, or maximum practical deck size.

The current providers are OpenAI, Anthropic, and the offline identity adapter. Legacy DeepSeek and Grok support is not part of the v2 provider surface. See [PROVIDERS.md](PROVIDERS.md).

## Translation memory

Translation memory is a local, persistent, unencrypted SQLite cache by default. It stores translated spans and may contain sensitive text. A symbolic-link cache leaf is rejected; parent resolution and POSIX no-follow/exclusive-create checks reduce common replacement races but do not isolate the cache from another process running as the same user. New POSIX cache directories and database files request owner-only mode bits, but this is not an ACL audit; existing permissions/ACLs are preserved, and Windows relies on filesystem ACL inheritance. SQLite uses `DELETE` rollback journaling to avoid persistent WAL/SHM sidecars, although a plaintext rollback journal can exist during a transaction or remain after a crash. Git ignore patterns cover matching untracked `.db`, `.sqlite`, `.sqlite3`, and journal paths, but they are not a confidentiality control and do not protect already tracked or unusually named databases. Keep custom `--memory` paths outside a checkout or add the exact name to that checkout's ignore rules. The cache has no built-in expiry, encryption, multi-user access control, synchronization, conflict resolution, or cache-management CLI. Use `--no-memory` to disable it and verify effective access controls and retention externally.

The semantic key prevents reuse when known meaning-bearing inputs change, but a schema-valid row written by another process is not cryptographically authenticated.

## Review and rendering status

The repository contains a safety-oriented review foundation:

- whole-deck LibreOffice-to-PDF rendering with hidden slides explicitly included;
- optional PyMuPDF rasterization;
- bounded PNG validation;
- strict provider-neutral issue schemas;
- local score/pass evaluation;
- privacy modes, endpoint checks, log redaction, budgets, and allowlisted repair-plan schemas.

It does **not** yet contain a multimodal review-provider adapter, an end-to-end comparison workflow, a CLI review command, or code that applies repair plans to a deck. No automatic visual review or automatic layout repair should be claimed for `2.0.0a1`.

LibreOffice rendering requires a separately installed LibreOffice executable and the `review` extra. Hidden slides are deliberately exported so page-count checks cover the complete deck, but rendering can still differ from Microsoft PowerPoint due to fonts, layout engines, linked resources, and platform behavior. The renderer's isolated profile and resource controls are not an OS sandbox.

The renderer copies the source once into a private per-run directory and performs hashing, slide counting, conversion, and rasterization against that snapshot. This narrows source-path TOCTOU exposure but cannot defend against a compromised host, storage subsystem, or process with access to the private directory.

## Security and privacy limits

PPTrans is not a malware scanner or content-disarm system. It preserves opaque and external package content rather than removing it. Opening output in PowerPoint or rendering an untrusted deck can expose the viewer/renderer to content PPTrans never interpreted.

Cloud providers receive selected text, adjacent context, language/style settings, and glossary content. Local translation memory and retained rendered images are plaintext. See [THREAT_MODEL.md](THREAT_MODEL.md) and [SECURITY.md](../SECURITY.md) before processing confidential or untrusted material.

Built-in paid-provider clients ignore ambient proxy and TLS-routing environment settings via `trust_env=False`, but an explicitly injected client may use different routing, and neither mode defeats host/network interception. Human-facing CLI values escape Unicode control characters and machine JSON is ASCII-escaped, but consumers must still treat all emitted data as untrusted.

## Release status

Version `2.0.0a1` is unreleased development work. It is not a release candidate, and the unresolved provenance/licensing gate in [NOTICE.md](../NOTICE.md) must be addressed before another package or release is published. See [CHANGELOG.md](../CHANGELOG.md) for the current alpha scope.
