# Jenkins CI integration

Jenkins runs beside the Fortify lab at `https://jenkins.DOMAIN`, behind the same
lab TLS certificate as SSC and ScanCentral. Its build agents trust the lab root
CA and come with the Fortify CLI (fcli), Apache Maven, and JDK 21, so pipelines can call
`https://ssc.DOMAIN` and `https://sast.DOMAIN` without certificate errors.

Jenkins is optional. It lives in the wizard's **Integrations** menu (`i` on the
main menu), not in the guided deployment, so lab lifecycle controls,
deployment profiles, and Flight Plans never start, stop, or upgrade it.

## What gets deployed

| Piece | Details |
| --- | --- |
| Controller | Official `jenkins/jenkins` Helm chart, release `jenkins` in the lab namespace, pinned by `FORTIFY_JENKINS_CHART_VERSION` and `FORTIFY_JENKINS_IMAGE_TAG` |
| URL | `JENKINS_URL` (default `https://jenkins.DOMAIN`), Ingress class `public`, TLS Secret `tls` |
| Admin login | `JENKINS_ADMIN_USER` (default `admin`) with `JENKINS_ADMIN_PASSWORD`, or `DEFAULT_PASS` when unset; stored in Secret `jenkins-admin` |
| Agents | Kubernetes pod agents with label `fortifylab`, up to `JENKINS_AGENT_MAX` at once, image pinned by `FORTIFY_JENKINS_AGENT_IMAGE_TAG` |
| Build tools | JDK 21 (in the agent image), plus fcli and Maven installed onto the shared tools volume and put on `PATH` |
| Data | PVC `jenkins-home` (8 Gi) for jobs and history; PVC `jenkins-agent-tools` (2 Gi, shared by agents) for fcli, Maven, and other tools |

Both PVCs are created outside Helm, so removing Jenkins keeps them unless you
confirm deleting data.

## Before you start

1. Complete the TLS certificates and Kubernetes Secrets steps. Jenkins reuses
   Secret `tls` and `ROOTCA_CERT` (`certs/rootCA.pem`).
2. Make `jenkins.DOMAIN` resolve to the lab node on your browser machine. The
   wizard's DNS helper (More tools -> Advanced setup and configuration ->
   Configure -> DNS) prints a hosts line that now includes it. Pods resolve it
   through the lab's CoreDNS mapping automatically.
3. Bring-your-own certificates must cover `jenkins.DOMAIN`, as an exact name
   or a wildcard such as `*.example.test`. Start refuses to deploy otherwise.
   The default mkcert certificate is a wildcard and always covers it.

Jenkins needs about 1–3 GiB of memory for the controller and up to 2 GiB per
running agent.

## Start, stop, remove

From **Integrations -> Jenkins CI**:

- **Start / upgrade** runs `apps/jenkins/start.sh`, then waits for the
  StatefulSet rollout and the login page. Re-run it after changing Jenkins
  settings in `.env` or rotating the lab CA.
- **Stop** scales the controller to zero. Data stays.
- **Remove** uninstalls the Helm release. A second question decides whether to
  delete the `jenkins-home` and `jenkins-agent-tools` volumes too.

## How agents trust the lab

Every agent pod runs an init container (`apps/jenkins/agent-init.sh`) before
the build starts. It builds a trust bundle from the image's default public CAs
plus the lab root CA (`ROOTCA_CERT`; the operator CA chain in BYO mode), so
builds can reach the lab and public sites such as GitHub and Maven Central.
Trusting only the lab CA would break public downloads.

The agent container is set up so common tools use that bundle:

| Tool | Setting |
| --- | --- |
| Java, Maven, Gradle | `JAVA_TOOL_OPTIONS` points at `/fortifylab-trust/cacerts`, so Maven trusts the lab and Maven Central |
| git, curl, OpenSSL | `GIT_SSL_CAINFO`, `CURL_CA_BUNDLE`, `SSL_CERT_FILE` -> `/fortifylab-trust/ca-bundle.crt` |
| Python requests | `REQUESTS_CA_BUNDLE` -> the same bundle |
| Node.js | `NODE_EXTRA_CA_CERTS` -> `/fortifylab-trust/rootCA.pem` |
| fcli | its own truststore setting, in `FCLI_DATA_DIR=/fortifylab-trust/fcli-data` |

The controller gets the same bundle, so plugins and webhooks can call lab URLs.

## fcli on agents

`FORTIFY_JENKINS_FCLI_INSTALL` controls fcli:

- `auto` (default): the init container downloads
  `fcli-linux.tgz` for `FORTIFY_JENKINS_FCLI_VERSION` (defaults to the lab's
  `FORTIFY_RECOMMENDED_FCLI_VERSION`) from
  [fcli releases](https://github.com/fortify/fcli/releases), verifies its
  `.sha256` checksum, and installs it onto the shared tools volume. Later
  agents reuse it, so it downloads once per version. If the download fails,
  for example on an offline lab, the build still runs without fcli.
- `manual`: nothing is downloaded. `/fortifylab-tools/bin` stays writable and
  first on `PATH`, so you can install fcli yourself and later builds keep it.

Manual install from a pipeline step:

```bash
version=3.23.3
cd "$(mktemp -d)"
curl -fsSLO "https://github.com/fortify/fcli/releases/download/v${version}/fcli-linux.tgz"
curl -fsSLO "https://github.com/fortify/fcli/releases/download/v${version}/fcli-linux.tgz.sha256"
sha256sum -c fcli-linux.tgz.sha256
tar -xzf fcli-linux.tgz -C /fortifylab-tools/bin fcli
fcli config truststore set --file "$FORTIFYLAB_JAVA_TRUSTSTORE" --type jks --password changeit
```

Later agents set the fcli truststore automatically when fcli is present.

## Maven on agents

Agents run Maven on the agent image's JDK 21, which includes `javac`. The init
container installs Apache Maven `FORTIFY_JENKINS_MAVEN_VERSION` (default
`3.9.16`) from Maven Central, checks its SHA-512 checksum, and links `mvn`
into `/fortifylab-tools/bin`. Like fcli, it downloads once per version per
tools volume. Set `FORTIFY_JENKINS_MAVEN_VERSION=""` to skip Maven.

Dependencies download on every build because each agent pod starts with an
empty `~/.m2`.

## Example pipeline

`git` checks out `master` unless you name a branch, so set `branch` for
repositories whose default branch is `main`:

```groovy
pipeline {
  agent { label 'fortifylab' }
  stages {
    stage('Build') {
      steps {
        git url: 'https://github.com/fortify/IWA-Java.git', branch: 'main'
        sh 'mvn -B clean verify'
        sh 'fcli --version'
      }
    }
  }
}
```

`withMaven { ... }` also works if you install the Pipeline Maven Integration
plugin (`pipeline-maven`); it finds `mvn` on `PATH`.

Replace `fortifydemo.com` with your `DOMAIN`. Add SSC credentials with the
Jenkins credentials store, never in the pipeline source.

## Troubleshooting

- **Browser shows `TRAEFIK DEFAULT CERT` or a 404:** `jenkins.DOMAIN` resolves
  somewhere other than the lab node. Fix client DNS or the hosts entry.
- **Start fails with "does not cover jenkins.DOMAIN":** the BYO certificate
  lacks the SAN. Reissue it with the name or a wildcard.
- **`Couldn't find any revision to build`:** the `git` step looked for
  `master`. Add `branch: 'main'` (or the repository's default branch).
- **Jenkins stuck in `Init:CrashLoopBackOff` after a host restart, with
  `cp: overwrite '/var/jenkins_plugins/…'?` in the `init` log:** the chart's
  plugin copy fails when the pod restarts in place. Start / upgrade adds a
  step that prevents this, and replaces a `jenkins-0` that is stuck on an old
  revision (a StatefulSet never replaces a pod that isn't ready, so the
  upgrade would otherwise hang). To recover by hand, run
  `microk8s kubectl -n NAMESPACE delete pod jenkins-0`. Data on `jenkins-home`
  is kept.
- **`mvn: not found`:** Jenkins was started before Maven support was added, or
  `FORTIFY_JENKINS_MAVEN_VERSION` is empty. Re-run **Start / upgrade**.
- **fcli or Maven missing on an agent:** open the agent pod's `fortifylab-init`
  container log in the build console or with
  `microk8s kubectl -n NAMESPACE logs <agent-pod> -c fortifylab-init`.
