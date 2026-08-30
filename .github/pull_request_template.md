## Change

Describe the user-visible outcome, the implementation boundary, and any compatibility impact.

## Evidence

List the exact focused and complete commands run, their results, and every skipped gate with a reason.

## Risk and claim check

- [ ] Input decks remain no-clobber, and temporary or failure artifacts are bounded and cleaned.
- [ ] Provider output, OOXML, paths, and caches affected by this change are treated as untrusted.
- [ ] Tests cover the changed contract, including relevant failure behavior.
- [ ] Documentation, limitations, threat boundaries, and the changelog are updated or not applicable.
- [ ] No credential, customer deck, provider payload, translation cache, or generated private artifact is included.
- [ ] No release, publication, or external mutation is implied; `NOTICE.md` still controls provenance.
