# PPTrans engineering case study

The one-page [PPTrans engineering case study](../../output/pdf/PPTrans-Engineering-Case-Study.pdf) is a self-contained job-application attachment. It is deliberately labeled as an unreleased, non-public local v2 showcase and does not link the legacy public `main` branch as though that branch contained the audited v2 implementation.

The [claim ledger](pptrans-engineering-case-study.json) is the canonical inventory for every number rendered into the PDF. It pins the dated verification commit, machine-readable source location or locations, and narrow scope for each claim. The generator independently reconciles the local suite, coverage, property-example, and provider-preview claims against the [local test audit](../qa/2026-08-31-local-test-audit.json), then checks the demo, benchmark, package, and compatibility sources rather than trusting display strings.

## Rebuild and check

Install the development dependencies, then build or verify the tracked artifact:

```bash
python scripts/build_case_study.py
python scripts/build_case_study.py --check
```

The builder uses invariant ReportLab output, fixed A4 geometry, base PDF fonts, fixed visual inputs, and no current time, username, absolute path, or network data. `--check` requires a byte-identical rebuild and validates the final PDF structure, metadata, selectable text, one-page media box, and absence of forms, annotations, attachments, JavaScript, launch actions, encryption, and external links.

## Scope and visual review

The English and Simplified Chinese images are exact LibreOffice 26.8.0.3 renders of the repository's synthetic fixture. They demonstrate real changed text through the stable-ID patch and verification path. They do not establish provider translation quality, Microsoft PowerPoint pixel identity, universal layout fit, or maximum practical deck size.

Render the final PDF at 200 DPI and inspect the complete page at original resolution. The current [case-study QA record](../qa/2026-08-31-case-study.json) pins the PDF, builder, ledger, local test audit, renderer, raster dimensions and hash, selectable-text checks, and visual result. Add a new no-clobber JSON record whenever the artifact or any pinned source changes. Disposable renders belong under `tmp/pdfs/` and must not be committed.

The artifact, its generator, and its evidence ledger are maintained inside this guarded source tree. Their presence does not resolve the inherited-project provenance question or authorize a package/release; [NOTICE.md](../../NOTICE.md) remains controlling.
