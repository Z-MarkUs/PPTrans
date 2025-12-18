# Language Support & Default Models

## Default Models by Provider

| Provider | Default Model | Notes |
|----------|---------------|-------|
| **DeepSeek** | `deepseek-chat` | Default provider (if no `--provider` specified) |
| **OpenAI** | `gpt-5` | Can override with `--model` flag |
| **Anthropic** | `claude-3.7-sonnet` | Can override with `--model` flag |
| **Grok** | `grok-beta` | Can override with `--model` flag |

### Default Provider
- If no `--provider` is specified, **DeepSeek** is used by default
- Default model for DeepSeek: `deepseek-chat`

### Overriding Default Models
You can override any provider's default model using the `--model` flag:
```bash
pptrans deck.pptx --provider openai --model gpt-4o
pptrans deck.pptx --provider anthropic --model claude-3-opus
```

## Language Support

### Language Code Format
PPTrans uses **ISO 639-1** language codes (2-letter codes) for language specification.

### Default Languages
- **Source Language**: `zh` (Chinese) - default
- **Target Language**: `en` (English) - default

### Supported Languages
**PPTrans does not restrict language codes** - it accepts any ISO 639-1 language code and passes it to the LLM provider. The actual language support depends on the capabilities of your chosen LLM provider.

#### Common Language Codes

| Code | Language | Code | Language |
|------|----------|------|----------|
| `zh` | Chinese | `en` | English |
| `ja` | Japanese | `ko` | Korean |
| `es` | Spanish | `fr` | French |
| `de` | German | `it` | Italian |
| `pt` | Portuguese | `ru` | Russian |
| `ar` | Arabic | `hi` | Hindi |
| `nl` | Dutch | `sv` | Swedish |
| `pl` | Polish | `tr` | Turkish |
| `vi` | Vietnamese | `th` | Thai |

### Examples

```bash
# Chinese to English (default)
pptrans deck.pptx --provider openai

# Japanese to English
pptrans deck.pptx --provider openai --source-lang ja --target-lang en

# English to Spanish
pptrans deck.pptx --provider openai --source-lang en --target-lang es

# French to German
pptrans deck.pptx --provider openai --source-lang fr --target-lang de

# Korean to Japanese
pptrans deck.pptx --provider openai --source-lang ko --target-lang ja
```

### Language Support Limitations

1. **Provider-Dependent**: Language support depends on your chosen LLM provider's capabilities
   - Most modern LLMs (GPT-4, Claude, etc.) support 50+ languages
   - Check your provider's documentation for specific language support

2. **No Validation**: PPTrans does not validate language codes - it passes them directly to the LLM
   - Invalid codes may result in translation errors
   - Use standard ISO 639-1 codes for best results

3. **Bidirectional**: Most language pairs are supported bidirectionally
   - `zh` ↔ `en` works both ways
   - `ja` ↔ `en` works both ways
   - etc.

### Best Practices

1. **Use ISO 639-1 codes**: Standard 2-letter language codes
2. **Check provider docs**: Verify your provider supports the language pair
3. **Test first**: Try a small file before processing large batches
4. **Use glossary**: For domain-specific terms, use `--glossary` flag

## Quick Reference

### Default Command (Chinese → English)
```bash
pptrans presentation.pptx --provider deepseek
```

### Custom Language Pair
```bash
pptrans presentation.pptx --provider openai --source-lang <CODE> --target-lang <CODE>
```

### View Help
```bash
pptrans --help
```
