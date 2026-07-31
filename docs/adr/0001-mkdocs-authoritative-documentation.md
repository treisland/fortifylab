# ADR 0001: Use MkDocs Material for authoritative documentation

- Status: Accepted
- Date: 2026-07-31
- Decision owners: Fortify Lab Manager maintainers
- Related issue: [#1](https://github.com/treisland/fortifylab/issues/1)

## Context

The repository already has a concise README, offline wizard help, and
operational Markdown. The documentation needs a searchable learning and
reference site without allowing those surfaces, or a separately maintained
GitHub Wiki, to become competing sources of truth.

This repository deploys an evaluation, demonstration, and training lab. Its
documentation must not imply that the single-node architecture is a production
deployment pattern. It must also remain safe to publish: credentials, tokens,
license content, private keys, customer data, production source, scan results,
private hostnames, and unredacted diagnostics are prohibited.

## Decision

MkDocs Material will render the authoritative long-form documentation from
version-controlled Markdown in `docs/`. Documentation changes follow the same
branch, pull-request, review, and validation process as code.

The documentation surfaces have these boundaries:

- `docs/` is authoritative for concepts, procedures, operations, reference,
  safety, architecture decisions, and contribution guidance.
- `README.md` is the concise repository entry point. It gives orientation and a
  quick start, then links to authoritative pages instead of duplicating them.
- `docs/help/` remains committed, concise, read-only offline help for the
  wizard. It must work without internet access, MicroK8s, or a healthy lab.
- Wizard messages use stable, path-like topic IDs, for example
  `troubleshooting/mysql-readiness`. A topic registry will map each ID to both
  an offline help resource and a site route. IDs are contracts: moving a page
  does not silently break a released wizard; an alias or redirect is required.
- A GitHub Wiki, if enabled, is informal only. Community notes, experiments,
  and workshop scratch material must link back to the authoritative site and
  must not define supported behavior.

The published site must repeat the lab/demo-only boundary in its landing page
and relevant operational guidance. Examples use synthetic data and placeholder
hosts only. The site build must never copy ignored runtime inputs, `.env`,
licenses, generated secrets, certificates, tokens, or diagnostics into its
artifact.

## Documentation flows

### Local

Contributors edit Markdown and configuration in the repository, preview the
site with the pinned project command, and run the documentation validation
suite. Offline wizard help continues to read committed files directly; local
site preview is optional for using the wizard. The MkDocs scaffold and exact
command are delivered separately from this architecture decision.

### Pull request and CI

Pull requests build MkDocs in strict mode and validate internal links,
navigation, stable topic mappings, safe example policy, and secret patterns.
CI builds an artifact but does not publish from an untrusted pull request.
Documentation and behavior that change together are reviewed and merged
together.

### Published

After a change reaches the protected publication branch, a least-privilege
GitHub Actions workflow builds the same pinned source and deploys its immutable
artifact to GitHub Pages. Concurrency prevents an older run from replacing a
newer site. Publication is a documentation delivery operation and cannot alter
the lab, Kubernetes cluster, or deployment scripts.

## GitHub Pages constraints for this repository

The repository was verified as **private** on 2026-07-31. The GitHub Pages API
returned `404 Not Found`, so no Pages site is currently configured. This is a
state observation, not evidence that the feature is unavailable.

GitHub documents that Pages from a private repository requires GitHub Pro,
Team, Enterprise Cloud, or Enterprise Server. A Pages site backed by a private
repository is not necessarily private: access-controlled private publication
requires an organization on GitHub Enterprise Cloud, while sites are public by
default in other supported configurations. Before enabling deployment, a
repository administrator must verify the owner plan and organization policy,
choose the intended site visibility explicitly, and confirm the resulting URL
from repository settings. No workflow should assume that repository visibility
protects the published content.

References (verified 2026-07-31):

- [Getting started with GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages)
- [Changing the visibility of your GitHub Pages site](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site)
- [Creating a GitHub Pages site](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/creating-a-github-pages-site)

## Alternatives considered

### GitHub Wiki as the authority

The Wiki is quick to edit, but its separate history and review flow make drift
from implementation more likely and weaken automated validation. It remains
suitable only for explicitly informal material.

### README and existing Markdown without a site generator

This preserves a minimal toolchain, but navigation, search, structured learning
paths, and consistent validation become harder as the documentation grows.

### Documentation embedded only in the wizard

This provides excellent offline proximity but is unsuitable for long-form
guidance, diagrams, cross-references, and browser search. It would also couple
content changes unnecessarily to shell UI behavior.

## Consequences

Positive consequences include reviewable documentation changes, reproducible
site builds, searchable navigation, automated contract checks, and one durable
source for both learners and operators. The wizard remains useful during an
outage or before installation.

Costs include maintaining a pinned documentation toolchain, route compatibility,
CI checks, and a small amount of intentionally concise offline content. Authors
must decide whether information belongs in long-form docs, offline help, or the
README and link across boundaries rather than copy text.

Publishing may remain unavailable until the repository plan and desired site
visibility are confirmed. A public site intentionally exposes all rendered
content even while its source repository is private.

## Security and operational implications

Documentation builds are static and must not contact a live cluster or require
licensed artifacts. Publishing receives only the permissions required by
GitHub Pages. Pull requests do not publish. Automated checks reduce, but do not
replace, human review for disclosure of sensitive screenshots or prose.

The lab-use disclaimer is a content contract. Documentation must distinguish
this lab automation from Fortify products' production capabilities and must not
offer a path that claims to convert this deployment into production.

## Migration and compatibility

Existing files under `docs/` remain valid inputs and can be reorganized
incrementally. Until the topic registry is implemented, current short wizard
topic names and `docs/help/` files remain supported. Introducing path-like IDs
must include aliases for released names and tests proving that every online and
offline target resolves.

README links should move to canonical site URLs only after Pages is confirmed;
repository-relative links remain the reliable fallback. Enabling MkDocs or
Pages changes documentation delivery only and does not change lab deployment,
configuration, persisted data, or secret handling.
