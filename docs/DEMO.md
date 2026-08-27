# Public demo source and QA

[`examples/pptrans-demo.en.pptx`](../examples/pptrans-demo.en.pptx) is a three-slide synthetic fixture for exercising the v2 pipeline without private presentation data, a network call, or an API key. It is not a translation-quality sample: the documented offline run uses the `identity` adapter, which returns source text unchanged.

![Rendered first slide of the synthetic PPTrans public demo](assets/pptrans-demo-preview.webp)

The preview is the first slide exported by the authoring runtime. It is useful for repository presentation and visual inspection, but it does not prove pixel identity with Microsoft PowerPoint or cover the other two slides.

## Committed evidence

[`tests/test_public_demo.py`](../tests/test_public_demo.py) runs the committed deck through inspection, identity translation, source-guarded patch construction, staged writing, verification, and an independent `python-pptx` reopen. Its current fixture contract is:

- 3 slides;
- 41 translation units;
- 45 translatable spans;
- no inspection warnings;
- 41 verified patches and 45 verified spans; and
- core metadata identifying Hehan Zhao and describing the deck as synthetic.

Document properties are normalized by [`scripts/sanitize_demo_metadata.py`](../scripts/sanitize_demo_metadata.py):

| Property | Committed value |
| --- | --- |
| Creator / last modified by | `Hehan Zhao` |
| Title | `PPTrans v2 - verifiable OOXML translation demo` |
| Subject | `Synthetic fixture for PPTrans inspection, patching, and verification` |
| Description | `Author-owned synthetic content; contains no customer or private presentation data.` |
| Created / modified | `2026-08-28T00:00:00Z` |
| Application / format / slides | `PPTrans demo generator` / `Widescreen` / `3` |

This removes tool-default metadata; it is not a general metadata scrubber for arbitrary presentations.

## Authoring source

[`scripts/build_demo.mjs`](../scripts/build_demo.mjs) contains the complete slide-authoring source. It uses Codex's bundled `@oai/artifact-tool` runtime to generate the raw deck, per-slide PNGs, per-slide layout JSON, an inspection snapshot, and the first-slide WebP preview.

The authoring package is deliberately not a PPTrans runtime or Python development dependency. The build command therefore works only in an environment where the bundled `@oai/artifact-tool` module is already resolvable; the repository does not claim that this package can be installed from a public npm registry. The committed `.pptx` remains testable with PPTrans and `python-pptx` without that authoring runtime.

In a compatible Codex workspace, after making the bundled module resolvable according to that workspace's dependency setup, rebuild into a fresh disposable directory rather than over the committed fixture:

```bash
node scripts/build_demo.mjs .tmp-demo/pptrans-demo.raw.pptx .tmp-demo/qa
python scripts/sanitize_demo_metadata.py .tmp-demo/pptrans-demo.raw.pptx .tmp-demo/pptrans-demo.en.pptx
pptrans inspect .tmp-demo/pptrans-demo.en.pptx --source en --target en
python -m pytest -q tests/test_public_demo.py tests/test_repository_scripts.py
```

Review every generated PNG and its corresponding layout JSON for clipping, overlap, or off-slide content before replacing a committed artifact. Then rerun the full applicable gates in [QUALITY_GATES.md](QUALITY_GATES.md). Generated QA directories are review evidence, not runtime inputs, and should not be committed unless the repository explicitly chooses to retain a particular artifact such as the preview.

## Scope and provenance

The v2 demo content and authoring source are maintained as an author-owned synthetic fixture. That fact does not resolve the separate imported-code provenance and licensing ambiguity recorded in [`NOTICE.md`](../NOTICE.md). Do not use the demo's provenance as evidence that the entire Git history is cleared for redistribution or release.
