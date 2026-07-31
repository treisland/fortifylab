# Networking, URLs, and TLS

The configured `DOMAIN` creates `ssc`, `sast`, `dast`, `lim`, and `dashboard`
HTTPS names. Client DNS or hosts entries must point them to the lab node. Pods
also need the repository's documented CoreDNS mapping so service-to-ingress
traffic preserves the expected hostname.

TLS uses a lab-local mkcert CA. Import its public CA certificate only on
dedicated lab clients. A browser name error means DNS/hostname mismatch; an
untrusted issuer generally means the lab CA is not installed. Never solve
either problem by disabling verification. Regenerating certificates rotates
the trust root and requires clients to trust the new lab CA.

Check in order: client name resolution, node reachability, ingress readiness,
configured hostname, certificate name, then CA trust. Do not publish this
single-node lab directly to an untrusted network.
