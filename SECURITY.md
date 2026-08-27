# Security policy

PPTrans processes ZIP/XML office documents, sends selected text to optional cloud providers, persists an optional local translation cache, and can invoke LibreOffice for optional slide rendering. Each boundary can carry sensitive or hostile data.

The v2 code is currently `2.0.0a1` and unreleased. Security work targets the active v2 development branch. Published 1.x artifacts use the legacy architecture and should not be assumed to have the safeguards described in the v2 [threat model](docs/THREAT_MODEL.md).

## Report a vulnerability privately

Do not open a public issue containing a proof of concept, private presentation, credential, or exploitable detail.

Use GitHub's private vulnerability-reporting flow on the repository's **Security** tab when it is available. If that flow is unavailable, contact the maintainer through the [Z-MarkUs GitHub profile](https://github.com/Z-MarkUs) with a minimal, non-sensitive request to establish a private channel. Do not attach the affected deck until a private channel is agreed.

A useful report includes:

- the affected commit and PPTrans version;
- operating system and Python version;
- the smallest synthetic reproducer possible;
- expected and observed behavior;
- impact and realistic attack preconditions;
- whether the issue involves local parsing, provider traffic, translation memory, rendering, or generated output.

There is no promised response-time SLA. Please allow time to reproduce and coordinate a fix before public disclosure.

## Safe-use guidance

- Keep API keys in environment variables or a local dotenv file excluded from version control. Dotenv files are loaded only when selected with `--env-file`; they are never discovered implicitly. The built-in adapters pin official API endpoints, reject ambient SDK base-URL/custom-header routing overrides, and use default HTTP clients with `trust_env=False` so environment proxy and TLS-routing settings are not inherited. Deliberately injected Python clients are caller-owned. PPTrans does not need a credential for `inspect`, `doctor`, or the offline `identity` provider.
- Treat every cloud translation as a data export. The provider receives selected deck text, adjacent paragraph context, language settings, style instructions, and glossary terms. Review the provider's data policy and obtain authorization for sensitive material.
- OpenAI translation requests set `store=False`; that flag does not replace the provider's contractual privacy and retention terms. The Anthropic adapter has no equivalent PPTrans-side storage control.
- Translation memory is an unencrypted local SQLite database containing translated text. PPTrans rejects a symbolic-link cache leaf, requests owner-only mode bits for new POSIX cache paths, and uses `DELETE` rollback journaling, but path checks do not isolate same-account processes, mode bits are not an ACL audit, existing permissions/ACLs are preserved, and Windows relies on filesystem ACL inheritance. Use `--no-memory` for sensitive work, keep custom caches under a trusted parent, verify effective access controls on every platform, and delete the database and any crash-left `-journal` sidecar according to your retention policy.
- Treat untrusted presentations as potentially malicious. The OOXML core applies defensive ZIP/XML checks, but PPTrans is not a malware scanner or content-disarm tool.
- Run LibreOffice rendering for untrusted files only inside an OS-level sandbox or disposable environment. PPTrans supplies an isolated LibreOffice profile, resource limits, a timeout, argument-list invocation, and a redacted child environment; it does not provide an operating-system sandbox.
- Inspect the distinct generated output before distribution. The source is not overwritten, but external relationships, embedded objects, and opaque package parts are preserved rather than sanitized.

## Security properties of the v2 core

The current implementation is designed to:

- reject non-`.pptx`, unreadable, encrypted, digitally signed, duplicate-member, unsafe-path, symbolic-link, corrupt-member, duplicate-relationship/repeated-slide-reference, and over-limit packages before provider work, including dedicated XML-part and semantic slide/element/unit/span/character/diagnostic ceilings;
- parse XML without DTD loading, entity resolution, or network access;
- bind inspection and patching to the source SHA-256 and per-unit source digests;
- require exact unit and span IDs in original order from provider responses and cached entries;
- reject extra schema fields, blank or implausibly expanded translations, protected-token changes, and XML-forbidden characters;
- cap default provider work at 2,000 units, 100 logical calls, 2,000,000 source/context characters, 5,000,000 serialized characters across all batches, and 1,000,000 characters per individual request;
- keep translation-memory paths distinct from deck and configuration paths;
- patch a staged copy, verify package inventory and unchanged content, then atomically publish without clobbering unless overwrite permission is explicit; low-level patch/rewrite APIs also default to no-clobber and always reject destination symlinks;
- use parameterized SQLite statements;
- render Unicode control characters visibly in human CLI output and emit machine JSON as plain ASCII-escaped data without terminal styling;
- avoid `exec`, `eval`, and `compile` in the v2 package;
- copy render input once into a private per-run snapshot, then invoke LibreOffice with `shell=False`, an isolated profile, a timeout, size/page/pixel ceilings, an explicit hidden-slide PDF export, and a child environment stripped of likely credential variables.

These controls and their residual risks are documented in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Explicit non-guarantees

PPTrans does not guarantee translation correctness, visual fit, PowerPoint-identical LibreOffice rendering, universal OOXML compatibility, malware removal, secrecy from a selected cloud provider, or encryption of local artifacts. The optional review modules are a safety-oriented foundation, not a complete cloud-review workflow in the v2 CLI. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
