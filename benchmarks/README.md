# Deterministic core benchmark

This directory contains raw, versioned evidence for narrowly scoped PPTrans performance claims. The current harness measures one complete local transaction on the committed synthetic deck:

1. defensive package and slide inspection;
2. offline identity-provider orchestration;
3. source-guarded OOXML text patch construction and staging; and
4. post-write package, structure, planned-text, and untouched-text verification.

It does **not** measure a paid provider, network traffic, translation-memory behavior, token use, LibreOffice, rasterization, visual quality, translation quality, cost, or maximum practical deck size.

## Reproduce

Start from a clean checkout of the commit named in the result and use the recorded Python version. Write to a new path so earlier evidence cannot be replaced accidentally:

```bash
python scripts/benchmark_core.py \
  --input examples/pptrans-demo.en.pptx \
  --warmups 3 \
  --iterations 30 \
  --output benchmarks/results/<date>-<platform>-<python>.json
```

The script refuses to overwrite by default, rejects source/output aliases and symbolic-link destinations, stages the JSON beside its destination, and atomically publishes it. A result records the exact command, Git SHA and dirty state, input hash/size/counts, OS, architecture, processor string, Python version, warmups, iterations, median, p95, minimum, and maximum.

The current committed Windows result was generated from `4fb51de01e19c74a488c9010d9408db719cc633a` with `git_dirty: false`; the earlier `dd39e55f80c5127f1eebcfc0903b0ac1bf15420b` result remains immutable historical evidence. Treat comparisons across hardware, operating systems, Python versions, fixture revisions, or background-load conditions as directional only.
