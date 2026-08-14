# First-scan command examples

These examples generate local starter scripts for the first synthetic scan
handoff. They are intentionally placeholders: review the generated files and
compare each command with the Fortify CLI and ScanCentral client versions that
match your lab.

Generate scripts into a disposable working directory:

```bash
mkdir -p /tmp/fortifylab-first-scan
docs/examples/first-scan/generate-first-scan-scripts.sh /tmp/fortifylab-first-scan
```

The generated scripts use environment variables for URLs, application names,
tokens, and target URLs. If you deployed Juice Shop from the wizard's **Sample
applications** menu, export `JUICE_SHOP_URL` and the DAST starter can use it as
the default authorized target. Do not paste token values into the scripts,
commit generated files, or run the DAST script against any target unless you
have explicit written authorization.
