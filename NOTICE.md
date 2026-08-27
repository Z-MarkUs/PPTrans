# Provenance and licensing notice

PPTrans's Git history includes source imported in commit `2591035bd0dfa504d408722783234f1d4fca8388`. That commit message identifies [the `tristan-mcinnis/PPT-Translator-Formatting-Intact-with-LLMs` repository](https://github.com/tristan-mcinnis/PPT-Translator-Formatting-Intact-with-LLMs) as its source.

Subsequent repository history records substantial changes and additions by Hehan Zhao and other Git authors, including translation memory and glossaries, review workflows, rendering, packaging, and release automation. The current v2 work under `src/pptrans` introduces a source-guarded, text-node-only OOXML patch-in-place architecture with post-write verification. Those engineering changes do not by themselves establish independent authorship of every retained file or resolve rights in inherited material and repository history.

The upstream licensing record is ambiguous rather than silent. In upstream commit `87a1266f965290722491414df34a61dbe2e6ec98` dated 2025-09-21—before the import above—the README displayed an MIT badge and stated, “This project remains under the MIT License. See `LICENSE` for details.” That commit's tree did not contain the referenced root `LICENSE` file. As rechecked on 2026-08-28, GitHub's repository-license endpoint still returned no root license. A full MIT text now exists at `.claude/skills/ppt-translator/LICENSE.txt`, but it was added in upstream commit `b61437d3446705e34e19189bd7f43ed0a2ef6763` on 2026-01-14, after the PPTrans import, and its placement leaves its scope unclear.

This notice does not decide the legal effect of the README statement, the missing referenced terms, or the later nested license. The `LICENSE` file in this repository can apply only to material that its copyright holder had authority to license; it cannot by itself resolve rights in inherited upstream material.

The project therefore does not claim that the full repository is an original or clean-room implementation, and it does not claim that the upstream licensing question is resolved. Before publishing another package or release, the maintainer should obtain written clarification or permission from upstream confirming the applicable terms and scope for the material imported in 2025, then update this notice. If that cannot be obtained, qualified legal guidance is appropriate before redistribution.

This notice records technical provenance and is not legal advice.
