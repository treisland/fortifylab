# Networking, URLs, and TLS

The configured `DOMAIN` creates `ssc`, `sast`, `dast`, `lim`, and `dashboard`
HTTPS names. Client DNS or hosts entries must point them to the MicroK8s lab
node. Pods also need the repository's CoreDNS mapping so service-to-ingress
traffic preserves the expected hostname.

TLS defaults to a lab-local mkcert CA. `scripts/create-certs.sh` creates the
mkcert root material and a wildcard leaf for `DOMAIN` and `*.DOMAIN`;
`scripts/create-secrets.sh` stores that leaf in the Kubernetes TLS Secret
`fortify/tls`. Import only the public `certs/rootCA.pem` on dedicated lab
clients. Never copy or import private keys such as `rootCA-key.pem` or
`tls.key`.

## TLS modes

Set `FORTIFY_TLS_MODE` in `.env`:

- `mkcert` is the default local-lab mode. Fortify Lab creates the mkcert root,
  wildcard leaf, PKCS12/JKS keystore, truststore, and Kubernetes TLS Secret.
- `byo` uses operator-provided PEM files. Set `FORTIFY_BYO_TLS_CERT`,
  `FORTIFY_BYO_TLS_KEY`, and `FORTIFY_BYO_TLS_CA_CERT` to protected paths.
  The leaf certificate must have SAN entries covering `ssc`, `sast`, `dast`,
  `lim`, and `dashboard` under the configured `DOMAIN`, either as exact names
  or a one-label wildcard such as `*.example.test`.

In BYO mode, `scripts/create-certs.sh` validates the certificate, private key,
key pair match, and required SAN coverage before copying normalized artifacts
into `certs/`. `scripts/create-secrets.sh` repeats the generated cert/key/SAN
checks before changing Kubernetes Secrets. The scripts print paths and metadata
only; they must not display private key contents.

## MicroK8s ingress and Traefik

Current MicroK8s releases back the `ingress` addon with Traefik. Fortify Lab
keeps NGINX-compatible annotations for older clusters, and also applies
Traefik-native configuration:

- application ingresses request TLS routing;
- HTTPS backend services are annotated with Traefik service settings;
- a shared Traefik `ServersTransport` skips verification for lab-generated
  internal service certificates;
- SSC gets a Traefik buffering middleware for large uploads; and
- the Secrets step sets MicroK8s ingress's default certificate to `fortify/tls`.

That default-certificate hook is what prevents browsers from seeing
`TRAEFIK DEFAULT CERT` for valid lab hostnames. If certificates were regenerated
or the ingress addon was recreated, rerun the Secrets step or run:

```bash
microk8s enable ingress --default-ssl-certificate fortify/tls
```

Then verify the served certificate with SNI:

```text
openssl s_client -connect LAB_NODE_IP:443 -servername ssc.DOMAIN </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -ext subjectAltName
```

The issuer should be the mkcert development CA, not `TRAEFIK DEFAULT CERT`.

## Troubleshooting order

Check one layer at a time:

1. Client DNS or hosts entry resolves the configured hostname to the lab node.
2. The node is reachable on 443.
3. MicroK8s ingress has a host rule for the requested name.
4. The Kubernetes Service has ready endpoints.
5. Traefik presents the generated mkcert or BYO TLS certificate.
6. The dedicated lab client trusts the mkcert root CA or BYO CA chain.

A browser name error means DNS or hostname/SAN mismatch. An untrusted issuer usually
means the lab CA or BYO CA chain is not installed. `TRAEFIK DEFAULT CERT` means Traefik is still
serving its fallback certificate or the client reached a different proxy. A
plain 404 from Traefik usually means the host rule did not match. Never solve
these by disabling certificate verification.

If an external proxy, Pi-hole, OPNsense, or another DNS layer is in the path,
confirm it resolves every lab hostname to the MicroK8s node or intentionally
forwards SNI/Host to that node with matching routes and the lab certificate.
