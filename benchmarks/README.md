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

The script refuses to overwrite by default, rejects source/output aliases and symbolic-link destinations, stages the JSON beside its destination, and atomically publishes it. A v2 result records a normalized reproduction command, Git SHA and dirty state, input hash/size/counts, OS, architecture, processor string, Python version, warmups, every measured sample, and recomputable median, p95, minimum, and maximum.

The current committed Windows result was generated from `7cb4a1f496857319ab73c4c84f5f7daf7f955354` with `git_dirty: false` and the honest-status exact-rebuild `ZIP_STORED` fixture. The earlier `c45856c0a98cdd00e916a4dd51a16397457ab9a3`, `8b98a986f4d6c68ca9cd582c1b6ca384ff23806c`, `4fb51de01e19c74a488c9010d9408db719cc633a`, and `dd39e55f80c5127f1eebcfc0903b0ac1bf15420b` results remain immutable historical evidence; the two oldest used the prior compressed container. Treat comparisons across hardware, operating systems, Python versions, fixture revisions, package storage, or background-load conditions as directional only.
