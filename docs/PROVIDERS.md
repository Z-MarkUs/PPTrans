# Translation providers

PPTrans v2 exposes a small provider-neutral contract and three current adapters. Paid providers require an explicit model; PPTrans does not guess one because model names, capabilities, price, and availability change independently of this repository.

## Current adapters

| Provider | Credential | Model | Structured-output mechanism | Notes |
| --- | --- | --- | --- | --- |
| `openai` | `OPENAI_API_KEY` | Required with `--model` | Responses API strict JSON Schema | Sends `store=False`; validates returned JSON again locally |
| `anthropic` | `ANTHROPIC_API_KEY` | Required with `--model` | Messages API with exactly one forced `submit_translations` tool call | Rejects text-only, missing, wrong, or duplicate tool output |
| `identity` | None | Fixed `identity-v1` | Local deterministic object construction | Returns source text unchanged; useful for pipeline tests, not translation |

DeepSeek and Grok existed in the legacy project but do not implement the v2 exact-ID adapter contract. They are not current v2 providers.

## Installation boundary

The base installation supports inspection and the offline `identity` transaction without installing or importing either paid-provider SDK:

```bash
python -m pip install -e .
```

Install only the provider adapter you intend to use:

```bash
python -m pip install -e ".[openai]"
# or
python -m pip install -e ".[anthropic]"
```

The `dev` extra deliberately includes both SDKs so the complete adapter suite can run offline with injected clients. A missing selected SDK fails with install guidance before client construction. `pptrans doctor --provider openai` or `--provider anthropic` checks both the selected SDK package and credential presence without making a network request.

## CLI configuration

Create a local dotenv file only if desired:

```bash
cp .env.example .env
```

The CLI reads exported environment values. It never searches for a dotenv file implicitly; select one explicitly with `--env-file .env`. File values do not overwrite variables already exported by the process.

```bash
pptrans translate deck.pptx \
  --source en \
  --target fr \
  --provider openai \
  --model <explicit-model-name> \
  --env-file .env \
  --max-provider-units 2000 \
  --max-provider-calls 100 \
  --max-provider-source-characters 2000000 \
  --max-provider-request-characters 5000000 \
  --fail-on-warnings \
  --output deck.fr.pptx
```

Those four ceilings are the CLI defaults; spelling them out in an operational command makes cost policy reviewable. Raising one is an explicit opt-in. The complete plan is conservatively checked before a paid-provider client is constructed, and cache misses are checked again before provider work.

`--fail-on-warnings` promotes the inspector's emitted unsupported-content diagnostics to a blocking policy. When such a warning is present, translation stops before output preflight, provider construction, translation-memory access, or publication. The absence of an emitted warning is not an exhaustive PowerPoint-support or visual-fit guarantee; see [known limitations](LIMITATIONS.md).

For an offline transaction check:

```bash
pptrans translate deck.pptx \
  --source en \
  --target en \
  --provider identity \
  --no-memory \
  --fail-on-warnings \
  --output deck.identity.pptx
```

The identity output should preserve every package-part payload because it proposes unchanged text. It does not test translation quality or a cloud SDK.

The provider-specific doctor check reports the installed SDK version and only whether the relevant environment variable is set; it does not print the key or validate it with the provider.

## Exact request and response contract

The application groups text into paragraph-sized translation units while preserving each existing run as a span. A provider request contains:

- source and target language strings;
- optional style guidance;
- an ordered glossary of source, target, and optional note;
- ordered unit IDs;
- adjacent paragraph text on the same slide when present;
- ordered span IDs, source strings, and translatable flags.

The request does **not** contain the deck filename/path, whole-file hash, slide part, shape locator, raw XML, formatting properties, images, notes, relationships, or embedded files. This reduces the export surface, but the selected text, context, and glossary can still be confidential.

The provider must return every requested unit exactly once and in request order. Each unit must return every translatable span ID exactly once and in source order. It must not return locked field spans. Unknown fields and wrong types are rejected by strict schemas; missing, extra, duplicate, or reordered IDs are rejected by application validation. A translated string must be nonblank, contain only XML 1.0-valid characters, stay within both the schema length and an expansion bound, and preserve high-confidence URLs, email addresses, placeholders, and digit sequences.

All of that validation happens before any provider batch or cache hit is accepted for patching, and before new provider output is written to translation memory. The patch stage independently checks exact IDs and source guards again.

## Batching and usage accounting

The default batch is 24 paragraph units. The accepted application range is 1–200. Default run ceilings are:

| Budget | CLI option | Default | What is counted |
| --- | --- | ---: | --- |
| Provider units | `--max-provider-units` | 2,000 | Translation units eligible to be sent |
| Logical calls | `--max-provider-calls` | 100 | Application batches; SDK-internal retries are separate |
| Source/context characters | `--max-provider-source-characters` | 2,000,000 | Source spans plus repeated neighboring context |
| Total serialized request characters | `--max-provider-request-characters` | 5,000,000 | Complete JSON documents across logical batches, including repeated style/glossary fields |

Every individual serialized request also has a fixed 1,000,000-character safety ceiling. Both paid adapters default to a 16,000 output-token ceiling and reject a configured ceiling below 256. These are cost and resource guards, not token estimates or promises that a provider will accept or complete a maximum-size request.

Provider token usage is normalized when the SDK returns valid nonnegative integers. If any batch lacks complete input or output usage, the run-level totals are reported as unknown instead of presenting a partial number as complete.

SDK construction currently uses a 120-second timeout and up to two SDK retries. Those retries are SDK behavior and are not counted as additional logical calls in PPTrans statistics; PPTrans does not treat a partial response as success.

Built-in provider clients pin `https://api.openai.com/v1` or `https://api.anthropic.com`. They reject ambient `OPENAI_BASE_URL`, `OPENAI_CUSTOM_HEADERS`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_CUSTOM_HEADERS` values so a credential and deck text cannot be silently redirected by generic SDK configuration. Their default HTTP clients use `trust_env=False`, so HTTPX does not inherit environment proxy or TLS-routing settings. This does not bypass host, network, or provider monitoring. Advanced Python callers can inject an already-configured client deliberately; that client's routing, proxy, trust-store, headers, and data boundary are then the caller's responsibility.

## Translation memory identity

The optional SQLite memory cache uses a SHA-256 key over all inputs that can change translation meaning:

- a deterministic translation-contract fingerprint derived from the exact provider system instructions and strict response schema;
- source/target language;
- provider/model;
- style;
- ordered glossary and notes;
- adjacent context;
- source strings, span kinds, translatability, ordering, and segmentation.

Deck path, deck hash, and batch size are omitted, enabling exact reuse across equivalent contexts in different decks. A prompt or response-schema change alters the contract fingerprint; any other known semantic change also creates a cache miss. Cache payloads are validated, but they are stored as unencrypted local text.

The cache path's symbolic-link leaf is rejected. On POSIX, each newly created parent directory requests mode `0700`, a newly created database requests `0600` (or stricter under the process umask), and the regular file is reopened without create permission before SQLite connects. Existing permissions and ACLs are deliberately not rewritten. Windows relies on inherited filesystem ACLs. SQLite is forced to `DELETE` rollback-journal mode, avoiding persistent WAL/SHM plaintext sidecars after successful transactions; a plaintext rollback journal can still exist during a transaction or remain after a crash. These controls reduce common exposure and path-race hazards but are not encryption, an ACL audit, or protection from another same-account process.

Use `--no-memory` when plaintext persistence is inappropriate. See [ARCHITECTURE.md](ARCHITECTURE.md#3-key-translation-memory-by-meaning) and [THREAT_MODEL.md](THREAT_MODEL.md#sqlite-corruption-or-injection).

## Provider privacy and failure behavior

Provider calls are network data exports. Confirm authorization, residency requirements, and retention terms before sending sensitive presentations. OpenAI's `store=False` setting narrows one service behavior but is not a general privacy guarantee. The Anthropic adapter does not set a comparable PPTrans-side retention option.

SDK and translation-memory failures are wrapped in concise PPTrans errors so exception details containing request, translation, or path content are not copied into the displayed message. Human-facing CLI values escape every Unicode `Cc` control character as visible `\uXXXX` text, except intentional newlines in inspected text. `--json` writes compact ASCII-escaped JSON directly to standard output without Rich markup, syntax highlighting, or terminal color. This does not control provider-side logs, SDK telemetry, caller-injected clients, network infrastructure, or operating-system monitoring.

## Adding an adapter

A new adapter must:

1. implement the `Translator` protocol with stable `provider` and `model` identifiers;
2. require an explicit paid model and credential;
3. serialize through the shared request document or document any deliberately different boundary;
4. force or strongly constrain structured output;
5. parse with the strict shared schema and return provider-neutral immutable values;
6. avoid logging credentials or request bodies in user-facing errors;
7. include offline tests for correct schema use, malformed/partial/ambiguous output, SDK failures, usage normalization, configuration, and real-SDK HTTP serialization/response parsing through an in-memory transport at current and declared-minimum versions;
8. document retention controls and any custom endpoint behavior.

Do not add a provider based only on an OpenAI-compatible base URL. Compatibility must be demonstrated at the exact request, schema, error, and usage boundaries. Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and the provider gate in [QUALITY_GATES.md](QUALITY_GATES.md).
