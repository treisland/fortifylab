# Configuration

Configuration is split across a few authoritative guides:

- [Secrets and licenses](../operations/secrets-and-licenses.md) covers protected
  inputs, external license paths, generated material, and safe handling.
- [Networking, URLs, and TLS](../operations/networking-and-tls.md) covers domain,
  DNS, ingress, certificates, and client trust.
- [Versions and compatibility](../operations/versions-and-compatibility.md)
  explains pinned images and upgrade checks.
- The repository `.env.example` is the version-controlled configuration
  template; `.env` is operator-owned and must not be committed.

Prefer the wizard's configuration menus over editing generated files. Never
paste credentials, tokens, license content, private keys, or unredacted
diagnostics into documentation or issues.
