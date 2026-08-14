# Phase 3 promotion gates

Phase 3 work lands on `integration/phase-3` first. Do not promote to `dev` or
`main` until manual testing accepts the integrated branch.

Required manual gates:

- run `./bin/fortifylab doctor --environment`;
- run `./bin/fortifylab config diagnostics --env .env`;
- run `./bin/fortifylab tui --demo-screen`;
- verify `./start_wizard.sh` still opens the Bash guided wizard;
- perform one clean guided deployment smoke test on a disposable lab host;
- verify diagnostics bundle output contains no secrets, license contents, or
  private key material;
- verify the companion web console is bound locally unless LAN access is
  explicitly enabled with a token.

Promotion path:

```text
integration/phase-3 -> dev -> main
```

Keep `main` and `dev` untouched until those gates are recorded in the release
notes for the promotion PR.
