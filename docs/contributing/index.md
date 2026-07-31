# Contributing

Documentation is code: change it on a non-default branch, review it in a pull
request, and validate it with the same pinned toolchain used by CI.

Before opening a pull request:

1. Keep one authoritative procedure and link to it from section landing pages.
2. Preserve existing routes and offline wizard topic files. If a route must
   move, add an explicit compatibility mapping and a regression test.
3. Keep examples synthetic and scan the change for credentials, tokens,
   licenses, private keys, customer data, production source, and diagnostics.
4. Run the full unit-test suite.
5. Build MkDocs in strict mode as described on the [site home](../index.md#run-the-strict-build).

Architecture decisions live under [ADRs](../adr/README.md). The
[documentation ADR](../adr/0001-mkdocs-authoritative-documentation.md) defines
the boundaries between the site, README, offline wizard help, and any informal
GitHub Wiki content.
