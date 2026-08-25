# Fortify Lab Help Center

These offline topics support the Python CLI/TUI help registry and the Fortify
Knowledge Center. They explain the lab
architecture without querying or changing the host, Kubernetes cluster,
credentials, or Fortify applications.

Start with:

- [System overview](overview.txt)
- [Dependencies and data flow](architecture.txt)
- [Software Security Center](ssc.txt)
- [ScanCentral SAST](sast.txt)
- [ScanCentral DAST](dast.txt)
- [License and Infrastructure Manager](lim.txt)
- [MySQL](mysql.txt) and [PostgreSQL](postgresql.txt)
- [Kubernetes Dashboard](dashboard.txt)
- [Roles and learning paths](roles.txt)
- [Glossary](glossary.txt)
- [URLs and interfaces](urls.txt)
- [Lab deployment versus Fortify products](lab-scope.txt)

Operational procedures, troubleshooting, recovery guidance, sanitized
diagnostics, and the first-scan walkthrough are under
[`docs/operations`](../operations/README.md). The mandatory lab/demo boundary
and acknowledgement behavior are documented in [Lab use](../lab-use.md).

Keep component names, dependency claims, URLs, and version-sensitive behavior
aligned with `./bin/fortifylab`, `.env.example`, and the corresponding tests.

## Stable topic IDs

Guided steps and troubleshooting failures refer to stable, path-like topic IDs,
such as `guided/mysql` and `troubleshooting/pending-pods`.
`fortifylab.help.HelpRegistry` and the catalog in `fortifylab.runbooks` expose
the Python-native lookup contract. Resolution only formats known strings: it
does not query MicroK8s, access credentials, inspect secret input paths, or make
network calls.

Set `FORTIFY_DOCS_BASE_URL` to the root of a trusted documentation deployment to
change every online link in one place. The value must begin with `https://` or
`http://`; the default is the project's GitHub Pages site. Offline help remains
available when the site or cluster is unavailable.

Topic IDs are compatibility contracts. When adding a guided step or a
troubleshooting choice, add its offline file and online route to all registry
columns and extend the completeness tests. When moving an online page, update
the route while retaining the topic ID. Do not place credentials, tokens,
license contents, private keys, or sensitive local paths in a mapping.
