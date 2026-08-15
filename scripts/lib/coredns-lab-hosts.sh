#!/bin/bash
# Keep in-cluster DNS aligned with the lab hostnames used by Fortify apps.

fortify_lab_node_ip() {
    hostname -I 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i !~ /^127\./) { print $i; exit } }'
}

fortify_lab_hostnames() {
    local domain="${DOMAIN:-fortifydemo.com}"
    printf '%s\n' "ssc.$domain" "sast.$domain" "dast.$domain" "lim.$domain" "dashboard.$domain" "lab.$domain" "juice-shop.$domain" "webgoat.$domain" "dvwa.$domain"
}

fortify_lab_hostnames_inline() {
    fortify_lab_hostnames | paste -sd ' ' -
}

fortify_patch_coredns_corefile() {
    local ip="$1" hosts="$2"
    awk -v ip="$ip" -v hosts="$hosts" '
        function print_block() {
            print "    # fortifylab hosts begin"
            print "    hosts {"
            print "        " ip " " hosts
            print "        fallthrough"
            print "    }"
            print "    # fortifylab hosts end"
        }
        function flush_hosts_block() {
            if (hosts_block ~ /(ssc|sast|dast|lim|dashboard|lab|juice-shop|webgoat|dvwa)\./) {
                print_block()
                managed=1
            } else {
                printf "%s", hosts_block
            }
            in_hosts=0
            hosts_block=""
        }
        /# fortifylab hosts begin/ {
            print_block()
            managed=1
            skip=1
            next
        }
        /# fortifylab hosts end/ { skip=0; next }
        skip { next }
        /^[[:space:]]*hosts[[:space:]]*{/ {
            in_hosts=1
            hosts_block=$0 "\n"
            next
        }
        in_hosts {
            hosts_block=hosts_block $0 "\n"
            if ($0 ~ /^[[:space:]]*}/) {
                flush_hosts_block()
            }
            next
        }
        /^}/ && !done && !managed {
            print_block()
            done=1
        }
        { print }
        END { if (in_hosts) flush_hosts_block() }
    '
}

fortify_ensure_coredns_lab_hosts() {
    local kubectl_cmd="${KUBECTL:-microk8s kubectl}"
    local ip hosts cm patched
    ip=$(fortify_lab_node_ip)
    hosts=$(fortify_lab_hostnames_inline)
    if [ -z "$ip" ]; then
        printf 'Could not determine the lab node IP for CoreDNS hosts override.\n' >&2
        return 1
    fi
    cm=$($kubectl_cmd -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}' 2>/dev/null) || true
    if [ -z "$cm" ]; then
        printf 'Could not read CoreDNS ConfigMap; pods may not resolve lab hostnames.\n' >&2
        return 1
    fi
    patched=$(printf '%s\n' "$cm" | fortify_patch_coredns_corefile "$ip" "$hosts")
    if [ "$patched" = "$cm" ]; then
        return 0
    fi
    printf '%s' "$patched" | $kubectl_cmd -n kube-system create configmap coredns \
        --from-file=Corefile=/dev/stdin --dry-run=client -o yaml \
      | $kubectl_cmd -n kube-system apply -f - >/dev/null
    $kubectl_cmd -n kube-system rollout restart deployment/coredns >/dev/null
    printf 'CoreDNS hosts override updated for: %s\n' "$hosts"
}
