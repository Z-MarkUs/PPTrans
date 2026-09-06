# PPTrans engineering case study

The one-page [PPTrans engineering case study](../../output/pdf/PPTrans-Engineering-Case-Study.pdf) is a self-contained job-application attachment. It identifies v2 as a **public-source pre-release engineering showcase** at `github.com/Z-MarkUs/PPTrans`, retains the project's upstream lineage, and makes no clean-room or unrelated-project claim. Public source availability is not a stable package release; no stable PPTrans v2 package release exists yet.

**Evaluate the project:** [product overview](../../README.md) | [English source deck](../../examples/pptrans-demo.en.pptx) -> [verified zh-CN output](../../examples/pptrans-demo.zh-CN.pptx) | [demo and QA notes](../DEMO.md) | [architecture](../ARCHITECTURE.md) | [known limitations](../LIMITATIONS.md)

The [claim ledger](pptrans-engineering-case-study.json) is the canonical inventory for every number rendered into the PDF. It pins the dated verification commit, machine-readable source location or locations, and narrow scope for each claim. The generator independently reconciles the local suite, coverage, property-example, and provider-preview claims against the [local test audit](../qa/2026-08-31-local-test-audit.json), then checks the demo, benchmark, package, and compatibility sources rather than trusting display strings.

## Rebuild and check

From a clean checkout with supported CPython 3.10-3.13, install the exact development extra, then build or verify the tracked artifact:

```bash
python -m pip install -e ".[dev]"
python scripts/build_case_study.py
python scripts/build_case_study.py --check
```

The builder uses invariant ReportLab output, fixed A4 geometry, base PDF fonts, fixed visual inputs, and no current time, username, absolute path, or network data. `--check` requires a byte-identical rebuild and validates the final PDF structure, metadata, selectable text, one-page media box, and absence of forms, annotations, attachments, JavaScript, launch actions, encryption, and external links. The repository address is intentionally plain selectable text, not an interactive PDF link.

## Scope and visual review

The English and Simplified Chinese images are exact LibreOffice 26.8.0.3 renders of the repository's synthetic fixture. They demonstrate real changed text through the stable-ID patch and verification path. They do not establish provider translation quality, Microsoft PowerPoint pixel identity, universal layout fit, or maximum practical deck size.

Render the final PDF at 200 DPI and inspect the complete page at original resolution. The current [case-study QA record](../qa/2026-09-06-case-study.json) pins the PDF, builder, ledger, local test audit, renderer, raster dimensions and hash, selectable-text checks, and visual result. Add a new no-clobber JSON record whenever the artifact or any pinned source changes. Disposable renders belong under `tmp/pdfs/` and must not be committed.

The artifact, its generator, and its evidence ledger are maintained in the public source tree. [NOTICE.md](../../NOTICE.md) records retained upstream attribution and licensing context. The case study describes a pre-release engineering showcase and does not claim that a stable package has been published.
