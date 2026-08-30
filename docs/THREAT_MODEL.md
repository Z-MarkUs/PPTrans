# Threat model

This threat model covers the current PPTrans v2 code in `src/pptrans`. It separates implemented controls from planned review capabilities. PPTrans is a document translator, not a malware scanner, sandbox, data-loss-prevention system, or cryptographic sanitizer.

## Assets to protect

- source presentation content and metadata;
- API credentials and local environment secrets;
- integrity of the source and generated presentation;
- local filesystem paths and existing destination files;
- translated text stored in SQLite;
- optional rendered slide images and shape manifests;
- provider budget and token usage;
- the host running LibreOffice.

## Trust boundaries and data flow

| Boundary | Data crossing it | Trust assumption |
| --- | --- | --- |
| Filesystem → OOXML core | ZIP members, XML, relationships, opaque embedded parts | Input may be malformed or hostile |
| Core → cloud translator | Languages, style, glossary, unit IDs, selected text spans, adjacent context | Provider and network are external; model output is untrusted |
| Core ↔ SQLite memory | Opaque semantic hash and translated span payload | Local database may be read, modified, or corrupted by another process |
| Core → output filesystem | Staged and final `.pptx` | Destination path may already exist; failures must not publish partial output |
| Core → LibreOffice | Complete local presentation path and sanitized process environment | LibreOffice is a large external parser, not a PPTrans sandbox |
| Renderer → optional future reviewer | Original/translated/overlay images and optional manifest fields | Upload is a separate, policy-controlled data export; no end-to-end adapter exists yet |

The built-in translation adapters do not upload the presentation binary, images, raw XML, slide-part paths, source file path, or source hash. They do upload selected slide text and nearby paragraph context, which can be sensitive on its own.

## Threats and implemented mitigations

### Malicious ZIP/OPC package

**Threats:** path traversal, absolute or drive-prefixed names, backslash ambiguity, duplicate entries, symbolic-link entries, encrypted data, decompression bombs, missing core parts, and signature invalidation.

**Mitigations:** member-name validation; duplicate, symlink, and encryption rejection; rejection of `_xmlsignatures/`; required-member checks; rejection of duplicate presentation-relationship IDs and repeated slide/relationship references; configurable limits for member count, per-member and per-XML-part expanded bytes, total expanded bytes, and compression ratio; semantic limits for slides, XML elements, units, spans, source characters, per-unit/per-span work, and diagnostics; and a full-member CRC read during inspection before provider construction. Relationships are resolved as normalized internal package paths before slide parts are read.

**Residual risk:** opaque package parts are preserved, not analyzed. A valid `.pptx` can retain external relationships, embedded objects, malformed content not traversed by PPTrans, or payloads that become relevant when another application opens the file. File extension alone is not a malware boundary.

### XML parser attacks

**Threats:** DTD/entity expansion, network retrieval, extremely large trees, malformed XML, and unexpected structural mutation during serialization.

**Mitigations:** DTDs are rejected; entity resolution, DTD loading, and network access are disabled; lxml's huge-tree mode is off; syntax failures are explicit. A canonical fingerprint masks only `a:t` content and translated whitespace metadata, then rejects any other structural difference. Independent text-node verification requires the exact `xml:space` semantics produced for every changed value, so a masked whitespace attribute cannot be altered freely.

**Residual risk:** parser and dependency vulnerabilities remain possible. Keep dependencies patched and use the configured dependency and CodeQL scans.

### Source changes and confused-deputy patches

**Threats:** applying an old provider result to a changed deck, resolving a paragraph after shape reordering, patching an invented unit, or changing an unplanned field.

**Mitigations:** the plan carries the source SHA-256; each unit carries a digest of its stable shape-ID locator and exact source spans. Hashes are checked across inspection, application, and verification. Patch construction rejects unknown/missing units and unknown/missing spans. Locator resolution and current source-span equality are checked immediately before assignment.

**Residual risk:** SHA-256 collision is treated as infeasible. A malicious process with permission to race and replace files on the host is outside PPTrans's isolation boundary; normal OS permissions still matter.

### Prompt injection and malformed provider output

**Threats:** source text instructs a model to ignore the task; the model returns prose, executable code, duplicate IDs, reordered spans, locked-field translations, oversized or extra data, or partial success.

**Mitigations:** instructions label deck JSON as untrusted data. OpenAI uses a strict JSON Schema response; Anthropic accepts exactly one content block and requires it to be the named schema tool call, rejecting accompanying prose or another tool call. Pydantic rejects extra fields and wrong types. Application validation requires exact unit/span identity and order, rejects blank, XML 1.0-invalid, oversized, or implausibly expanded text, and requires high-confidence URLs, emails, placeholders, and digit sequences to survive unchanged before memory writes. A contract fingerprint derived from the exact system instructions and response schema invalidates prior semantic cache keys when either contract component changes. The v2 package contains no `exec`, `eval`, or `compile` call, and a security test scans for them.

### Unbounded provider work or cost

**Threats:** a large or adversarial deck triggers excessive API calls, repeated context/glossary serialization, unexpectedly high cost, or a provider request too large for reliable handling.

**Mitigations:** the CLI checks the complete plan before constructing a paid-provider client, then checks cache misses again before provider work. Defaults cap provider units at 2,000, logical calls at 100, source/context characters at 2,000,000, and serialized request characters at 5,000,000 across the run. Every serialized batch has an independent 1,000,000-character ceiling. SDK retries are separately bounded and are not hidden inside the logical-call statistic.

**Residual risk:** character ceilings are not token or currency ceilings. Model pricing, tokenization, network retries, provider-side behavior, and quality vary. Raising a CLI ceiling is an explicit user decision and can increase cost.

**Residual risk:** a schema-valid translation can still be wrong, misleading, offensive, or contextually unsafe. Human review remains necessary for consequential content.

### Credential and sensitive-data disclosure

**Threats:** secrets appear in logs, exceptions, subprocess environments, commits, or cloud requests; private text persists locally or at a provider.

**Mitigations:** credentials come from explicit environment variables or a user-selected dotenv file; no dotenv file is discovered implicitly. Built-in adapters pin official API endpoints, reject ambient SDK base-URL/custom-header routing variables, and create default HTTP clients with `trust_env=False` so HTTPX does not inherit environment proxy or TLS-routing settings. Provider SDK errors are wrapped in generic messages. LibreOffice receives an environment with likely secret-bearing key names removed. Review helpers redact credential/image-like fields and secret-shaped strings from nested logging metadata. OpenAI requests set `store=False`.

**Residual risk:** SDKs and providers still receive credentials and translation content. `store=False` does not supersede provider terms, abuse monitoring, or network controls. Anthropic requests have no PPTrans-side storage flag. Host/network interception remains possible, and a deliberately injected Python SDK client owns its endpoint, headers, proxy, and trust-store behavior. Translation memory and retained rendered images are plaintext local artifacts. Redaction is pattern-based and cannot guarantee discovery of every secret.

### SQLite corruption or injection

**Threats:** hostile cache keys alter SQL, corrupt rows bypass validation, or a stale translation is reused under changed semantics.

**Mitigations:** all statements use bound parameters; cached JSON is validated through the same strict span schema and application text checks; semantic keying includes languages, provider, model, style, glossary, context, source, segmentation, and the prompt/schema-derived contract fingerprint. Invalid cache entries fail before a provider call or patch. The CLI and adapter reject a symbolic-link cache leaf. On POSIX, PPTrans requests mode `0700` for each missing cache directory and exclusively creates a new database with mode `0600` (or stricter under the process umask); it does not rewrite mode bits or ACLs on existing paths. The adapter reopens the prepared POSIX regular file without create permission and with `O_NOFOLLOW` when the platform provides it, then explicitly uses SQLite `DELETE` rollback-journal mode so successful transactions do not leave persistent WAL/SHM plaintext sidecars.

**Residual risk:** SQLite is not encrypted or authenticated. A rollback journal can transiently contain plaintext and can remain after a crash. Anyone with filesystem access can read translated text, delete entries, or cause denial of service. POSIX mode bits are not an ACL audit, and existing custom database paths retain their existing access controls. Windows relies on inherited filesystem ACLs and does not emulate POSIX modes. Users must verify effective ACLs and filesystem semantics on every platform and place custom caches under a trusted parent; a same-account process able to replace paths during opening is outside PPTrans's isolation boundary. PPTrans detects malformed payloads but does not prove who wrote a schema-valid cache row.

### Partial output or destination loss

**Threats:** a failed translation leaves a plausible but incomplete output, overwrites the source, or destroys an existing destination before verification.

**Mitigations:** source and output paths must differ by resolved path and filesystem identity; an existing destination requires explicit overwrite permission, and destination symbolic links are always rejected. These same alias/no-clobber/symlink rules apply to the public low-level patch and package-rewrite APIs. Destination validity and writability are checked before provider creation. The complete package is written to a temporary file in the destination directory, verified, and flushed. Default atomic publication refuses a destination that appears during the run; explicit overwrite uses atomic replacement. Private-stage cleanup retries transient Windows sharing failures within a fixed bound, and success is returned only after the stage is absent. Exhausted post-publication cleanup rolls back only an identity-matching final, preserves foreign replacements, and reports the exact final/staging residual state. An existing destination remains untouched until authorized final replacement.

**Residual risk:** PPTrans does not provide transactional recovery from every filesystem, hardware, or power failure. Backups and normal filesystem durability controls remain the user's responsibility.

### LibreOffice command and rendering attacks

**Threats:** shell injection through filenames, credential inheritance, profile contamination, runaway conversion, malicious document parser behavior, oversized PDFs/images, or forged raster output.

**Mitigations:** LibreOffice is invoked with an argument list and `shell=False`; filenames are not interpolated into a shell. Each run copies the input once into a private temporary directory and hashes, slide-counts, converts, and rasterizes that same snapshot, reducing source-path replacement races. The run also gets an isolated user profile, timeout, working directory, and sanitized environment. Impress PDF export explicitly includes hidden slides, and the renderer compares the resulting page count with the whole-deck count when available. Input/PDF byte limits, page count, DPI, aggregate pixel limits, Pillow decoding, PNG-format verification, decompression-bomb handling, staged image publication, and content hashes bound resource use and output identity.

**Residual risk:** the process is not placed in an OS sandbox, and an isolated LibreOffice profile is not a security sandbox. LibreOffice may resolve document features or contain parser vulnerabilities. Run it in a low-privilege disposable container/VM for untrusted decks. Rendering through LibreOffice can differ visually from PowerPoint.

### Terminal-control injection

**Threats:** hostile text or paths contain ANSI/OSC sequences or other control characters that alter a terminal, hide output, or corrupt machine-readable results.

**Mitigations:** human-facing values render every Unicode `Cc` control character as visible `\uXXXX` text, except intentional newlines in inspected text. JSON modes use compact `ensure_ascii=True` serialization written directly to standard output without Rich markup, syntax highlighting, or ANSI color.

**Residual risk:** downstream tools must still parse and display output safely. Unicode formatting characters outside category `Cc`, provider/OS logs, and external callers that bypass the CLI are outside this terminal boundary.

### Future cloud-assisted review and repair

**Threats:** unintended original-slide upload, manifest text leakage, arbitrary endpoint exfiltration, unbounded cost, model-controlled pass/fail, arbitrary code/property mutation, or repeated destructive repairs.

**Implemented foundation:** privacy modes select allowed image roles; manifest text is off by default; known provider endpoints require HTTPS and custom endpoints require explicit consent; budgets reserve requests/slides/pixels/tokens/repair rounds before work; strict observation schemas reject extra fields; score and pass/fail are computed locally; repair plans use bounded discriminated operations, known slide/shape IDs, and repeat fingerprints.

**Current boundary:** there is no multimodal provider adapter, review orchestrator, CLI review command, or repair executor. The controls above are tested building blocks, not evidence of a complete secure review workflow. A future implementation needs a new threat-model review before it can be advertised or enabled.

## Security assumptions

- The host OS, Python interpreter, installed dependencies, provider SDKs, and user account are not already compromised.
- The user chooses a provider and model they are authorized to use.
- The destination directory is trusted enough to hold the generated deck.
- Local access controls protect credentials, dotenv files, cache databases, and retained render artifacts.
- Dependency updates and security scans are reviewed rather than merged blindly.

## Verification evidence

The offline suite exercises malicious archive names and duplicate members, package limits, digital-signature rejection, locked fields, stale source hashes, structural and planned-whitespace tampering, unrelated-part changes, exact-ID failures, ambiguous provider content, authentication/rate-limit error mapping, cache corruption, SQL metacharacters, POSIX cache creation modes, SQLite journal policy, dynamic-execution absence, endpoint policy, log redaction, budget ceilings, renderer command construction, missing backends, and invalid images.

That coverage demonstrates known controls on synthetic inputs. It does not replace fuzzing, dependency review, an OS sandbox for office rendering, or independent security assessment. See [SECURITY.md](../SECURITY.md) for reporting and [QUALITY_GATES.md](QUALITY_GATES.md) for required checks.
