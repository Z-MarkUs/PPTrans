# Provider operation

Use this workflow only after the user has selected OpenAI or Anthropic, supplied an exact currently available model, and authorized sending the selected deck text to that provider.

## Review the export boundary

PPTrans sends selected slide text, adjacent paragraph context, source and target languages, and any supplied style or glossary terms. It does not send the PPTX binary, file path, raw XML, formatting, images, notes, relationships, or embedded files. The selected text and context can still be confidential.

Confirm applicable authorization, residency, retention, and cost requirements before the call. OpenAI requests set `store=False`, but that is not a general privacy guarantee. Do not treat an inspection or identity-test request as authorization for provider work.

## Inspect and preview before spending

Run a deck-text-free inspection with `--fail-on-warnings` before translation. Resolve warnings and confirm the output name, provider, model, language pair, glossary, style, persistence choice, and ceilings before the paid command.

Then preview the complete zero-memory-hit provider workload without loading credentials, a provider SDK, translation memory, an output path, or the network:

```bash
pptrans translate "deck.pptx" --source en --target fr --provider openai --model "EXACT_MODEL_NAME" --dry-run --max-provider-units 2000 --max-provider-calls 100 --max-provider-source-characters 2000000 --max-provider-request-characters 5000000 --fail-on-warnings --json
```

The deck-text-free preview still reports the source SHA-256, slide/unit/span counts, workload counts, and warnings; it emits neither the source path nor slide text. Its total units, calls, and character work are upper bounds assuming zero translation-memory hits. The largest and per-call request sizes describe that zero-hit batching; cache hits can regroup misses, and the real run revalidates them. It is not a token, currency, latency, model-availability, credential, provider-readiness, or translation-quality estimate. `--dry-run` rejects `--output`, `--overwrite`, `--env-file`, and `--memory`; do not weaken that boundary. An explicit glossary or style may be included when its effect on the estimate must be measured.

Review the preview before proceeding.

## Check the selected adapter

After accepting the preview, install only the adapter the user intends to use, and only in the intended environment. Then check its SDK and credential locally without sending a request:

```bash
pptrans doctor --provider openai
# or
pptrans doctor --provider anthropic
```

Use an exported `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, or pass a user-selected local file with `--env-file`. PPTrans never searches for dotenv files implicitly. `doctor` reports only whether the credential is present; it neither prints nor validates the key with the provider.

For a one-off or sensitive deck, use the following shape and retain the default ceilings explicitly:

```bash
pptrans translate "deck.pptx" --source en --target fr --provider openai --model "EXACT_MODEL_NAME" --no-memory --max-provider-units 2000 --max-provider-calls 100 --max-provider-source-characters 2000000 --max-provider-request-characters 5000000 --fail-on-warnings --output "deck.fr.pptx" --json
```

Substitute `anthropic` only when that adapter and credential were selected. Add `--env-file`, `--glossary`, or `--style` only for explicit inputs. Do not infer a model, raise a ceiling, enable translation memory, or replace an existing output to make a command proceed.

The four ceilings bound worst-case provider units, logical application batches, source/context characters, and serialized request characters. They are not token, price, runtime, or quality estimates. SDK-internal retries are separate from logical-call statistics.

## Stop and report safely

Do not blindly retry an authentication, throttling, malformed-response, timeout, partial-result, or ambiguous failure; another call can spend money and export text again. Inspect the error and destination state first, without printing request content or credentials. If success cannot be established, report it as unconfirmed rather than claiming completion.

On success, report the provider/model, output, hashes, verified spans, provider-call count, token usage when complete, memory choice, warnings, and exact review scope. Open the output in the target presentation application before treating layout or translation quality as accepted.
