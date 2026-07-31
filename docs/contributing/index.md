# Contributing

Documentation is code: change it on a non-default branch, review it in a pull
request, and validate it with the same pinned toolchain used by CI.

## One-command validation

Create the documentation environment once, then use the same offline gate as
CI. It does not contact Kubernetes or require a Fortify license:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements-docs.txt
./scripts/validate-docs.sh
```

The gate runs the strict MkDocs build and all unit tests. Its project-owned
validator also checks internal links and anchors, navigation coverage, selected
Markdown style rules, terminology and common spelling mistakes, Mermaid fence
structure, wizard offline/online topic mappings, shell-example syntax, unsafe
commands, tracked secret-file patterns, and likely credential values. External
links are deliberately not fetched, keeping the result reproducible and usable
offline.

Set `MKDOCS_BIN` to an alternate executable when using an isolated tool cache:

```bash
MKDOCS_BIN=/opt/docs-tools/bin/mkdocs ./scripts/validate-docs.sh
```

Before opening a pull request:

1. Keep one authoritative procedure and link to it from section landing pages.
2. Preserve existing routes and offline wizard topic files. If a route must
   move, add an explicit compatibility mapping and a regression test.
3. Keep examples synthetic and scan the change for credentials, tokens,
   licenses, private keys, customer data, production source, and diagnostics.
4. Run `./scripts/validate-docs.sh`.
5. Fix the reported source rather than weakening a gate. If a safe example
   cannot be expressed within a gate, document and test the narrow exception in
   the validator.

Wizard documentation uses the stable topic registry described in the
[offline Help Center](../help/README.md#stable-topic-ids). A new guided step or
troubleshooting symptom must include both offline and online mappings; tests
intentionally fail when a registry column or step mapping is missing.

Architecture decisions live under [ADRs](../adr/README.md). The
[documentation ADR](../adr/0001-mkdocs-authoritative-documentation.md) defines
the boundaries between the site, README, offline wizard help, and any informal
GitHub Wiki content.
