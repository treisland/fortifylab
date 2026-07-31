# Safety

Read the [lab and demo use boundary](../lab-use.md) before deploying. It defines
the required acknowledgement, prohibited production use and data, network
exposure cautions, and destructive-action warnings.

For documentation changes, the
[documentation architecture decision](../adr/0001-mkdocs-authoritative-documentation.md)
also defines the publication boundary: committed Markdown must never contain or
copy credentials, tokens, licenses, private keys, customer data, production
source, scan results, or unredacted diagnostics.

This repository's limitations apply to its single-node lab automation. They do
not describe or limit the production capabilities of Fortify products.
