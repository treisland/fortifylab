#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:-./fortifylab-first-scan}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
sample_source="$repo_root/docs/examples/sast/SyntheticGreeting.java"

mkdir -p "$output_dir/synthetic-source"
cp "$sample_source" "$output_dir/synthetic-source/SyntheticGreeting.java"

cat > "$output_dir/first-sast-scan.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

# Review this starter against the ScanCentral client and fcli versions deployed
# in your lab. All credentials stay in environment variables.
: "${SSC_URL:?Set SSC_URL, for example https://ssc.example.test}"
: "${SCSAST_CTRL_URL:?Set SCSAST_CTRL_URL, for example https://sast.example.test/scancentral-ctrl/}"
: "${SSC_APP_NAME:=Fortify Lab Training}"
: "${SSC_APP_VERSION:=Synthetic}"
: "${SYNTHETIC_SOURCE_DIR:=./synthetic-source}"
: "${FCLI_BIN:=fcli}"
: "${SCANCENTRAL_BIN:=scancentral}"
: "${FCLI_SSC_SESSION:=fortifylab-ssc}"
: "${SSC_CITOKEN:?Set SSC_CITOKEN to an SSC token with permission to create/upload scans}"
: "${SCSAST_CLIENT_AUTH_TOKEN:?Set SCSAST_CLIENT_AUTH_TOKEN from the protected SAST client token}"

"$FCLI_BIN" ssc session login --url "$SSC_URL" --ci-token "$SSC_CITOKEN" --session "$FCLI_SSC_SESSION"
"$FCLI_BIN" ssc appversion create "$SSC_APP_NAME:$SSC_APP_VERSION" --session "$FCLI_SSC_SESSION" --auto-required-attrs || true

pushd "$SYNTHETIC_SOURCE_DIR" >/dev/null
"$SCANCENTRAL_BIN" start \
  --url "$SCSAST_CTRL_URL" \
  --ssc-url "$SSC_URL" \
  --ssc-ci-token "$SSC_CITOKEN" \
  --client-auth-token "$SCSAST_CLIENT_AUTH_TOKEN" \
  --application "$SSC_APP_NAME" \
  --application-version "$SSC_APP_VERSION" \
  --upload \
  --quiet \
  --scan
popd >/dev/null

printf 'Submitted synthetic SAST source from %s. Verify the result in SSC: %s / %s\n' \
  "$SYNTHETIC_SOURCE_DIR" "$SSC_APP_NAME" "$SSC_APP_VERSION"
SCRIPT

cat > "$output_dir/first-dast-scan.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

# DAST product interfaces and automation flags vary by deployed version. This
# script performs the bounded handoff checks and prints the values to use when
# creating the conservative scan in the DAST UI or a version-matched fcli flow.
# If Juice Shop was deployed through the Sample applications menu, JUICE_SHOP_URL
# can provide the authorized target default. You still need an authorization note.
: "${SSC_URL:?Set SSC_URL, for example https://ssc.example.test}"
: "${SCDAST_URL:?Set SCDAST_URL, for example https://dast.example.test}"
: "${SSC_APP_NAME:=Fortify Lab Training}"
: "${SSC_APP_VERSION:=Synthetic}"
: "${AUTHORIZED_DAST_URL:=${JUICE_SHOP_URL:-}}"
: "${AUTHORIZED_DAST_URL:?Set AUTHORIZED_DAST_URL to your isolated, disposable target URL or deploy Juice Shop and export JUICE_SHOP_URL}"
: "${DAST_AUTHORIZATION_NOTE:?Set DAST_AUTHORIZATION_NOTE to your written authorization reference}"
: "${FCLI_BIN:=fcli}"
: "${FOD_URL:=}"
: "${FOD_TENANT:=}"

cat <<EOF
Create a conservative first DAST scan with these values:

  DAST URL:             $SCDAST_URL
  SSC destination:      $SSC_URL
  SSC app/version:      $SSC_APP_NAME / $SSC_APP_VERSION
  Authorized target:    $AUTHORIZED_DAST_URL
  Authorization note:   $DAST_AUTHORIZATION_NOTE

Scope limits:
  - exact host and authorized path only
  - lowest practical concurrency and request rate
  - no credentials unless the authorization names a synthetic account
  - no public, shared, production, or third-party targets

Use the DAST UI first unless your deployed Fortify version documents an fcli
DAST command for this flow. FoD is optional; set FOD_URL and FOD_TENANT only
when you deliberately choose a FoD workflow instead of SSC-primary lab results.
EOF
SCRIPT

chmod 700 "$output_dir/first-sast-scan.sh" "$output_dir/first-dast-scan.sh"

cat <<EOF
Generated first-scan starters:
  $output_dir/first-sast-scan.sh
  $output_dir/first-dast-scan.sh

Review the generated scripts before use. They contain placeholders only and
expect tokens/passwords through environment variables at runtime.
EOF
