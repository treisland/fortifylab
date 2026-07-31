# Publishing the documentation

The expected published site URL is
<https://treisland.github.io/fortifylab/>. The site and every page footer carry
the lab/demo-only notice. The published output contains only committed Markdown
from `docs/` and the static assets produced by MkDocs; it does not read runtime
configuration or any lab deployment input.

## Publication boundary

Pull requests and updates to `dev` run the documentation quality workflow and
build the site with strict validation, but they do not publish. After a human
approves the integration branch for `main`, a push to `main` runs the dedicated
Pages workflow. That workflow builds a fresh site and deploys the resulting
artifact. Its build job can only read repository contents, while its deployment
job receives only the `pages: write` and `id-token: write` permissions required
by GitHub Pages.

Publishing is deliberately independent of the deployment wizard and all lab
scripts. A Pages configuration, build, or deployment failure cannot install,
start, stop, or otherwise modify the Fortify lab.

## Private-repository prerequisite

This repository is private. GitHub Pages availability for a private repository,
and who can view the published site, depend on the repository owner's GitHub plan
and the Pages visibility options available to that account. Before the
first publication, an owner must:

1. confirm that the account plan supports Pages for this private repository;
2. select **GitHub Actions** as the Pages build and deployment source in the
   repository settings; and
3. choose a site visibility consistent with the lab's data-handling boundary.

Do not make the repository public merely to activate Pages. If Pages is not
available, use the [local preview](../index.md#preview-locally) while keeping the
repository private. The workflow intentionally fails closed until an owner has
configured a supported Pages environment.

## Validate before approval

Run the same one-command documentation gate used by pull requests:

```bash
./scripts/validate-docs.sh
```

Only an approved change on `main` is eligible to publish. The `github-pages`
concurrency group serializes deployments so an older run cannot cancel a newer
approved publication midway through deployment.
