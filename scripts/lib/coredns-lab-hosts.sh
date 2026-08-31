#!/bin/bash
# Keep in-cluster DNS aligned with the lab hostnames used by Fortify apps.

fortify_lab_node_ip() {
    hostname -I 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i !~ /^127\./) { print $i; exit } }'
}

fortify_lab_hostnames() {
    local domain="${DOMAIN:-fortifydemo.com}"
    printf '%s\n' "ssc.$domain" "sast.$domain" "dast.$domain" "lim.$domain" "dashboard.$domain" "juice-shop.$domain" "webgoat.$domain" "dvwa.$domain"
}

fortify_lab_hostnames_inline() {
    fortify_lab_hostnames | paste -sd ' ' -
}

fortify_local_hosts_block() {
    local ip="$1" hosts="$2"
    printf '%s\n' '# BEGIN FORTIFYLAB'
    printf '%s %s\n' "$ip" "$hosts"
    printf '%s\n' '# END FORTIFYLAB'
}

fortify_patch_local_hosts_file() {
    local ip="$1" hosts="$2"
    awk -v ip="$ip" -v hosts="$hosts" '
        function print_block() {
            print "# BEGIN FORTIFYLAB"
            print ip " " hosts
            print "# END FORTIFYLAB"
        }
        /^# BEGIN FORTIFYLAB$/ {
            if (!printed) {
                print_block()
                printed=1
            }
            skip=1
            next
        }
        /^# END FORTIFYLAB$/ { skip=0; next }
        skip { next }
        { print }
        END {
            if (!printed) {
                if (NR > 0) print ""
                print_block()
            }
        }
    '
}

fortify_remove_local_hosts_block() {
    awk '
        /^# BEGIN FORTIFYLAB$/ { skip=1; next }
        /^# END FORTIFYLAB$/ { skip=0; next }
        skip { next }
        { print }
    '
}

fortify_local_hosts_apply_file() {
    local file="$1" content="$2" backup
    backup="${file}.fortifylab.$(date +%Y%m%d%H%M%S).bak"
    if [ -w "$file" ]; then
        cp "$file" "$backup" || return 1
        printf '%s' "$content" > "$file"
    else
        sudo cp "$file" "$backup" || return 1
        printf '%s' "$content" | sudo tee "$file" >/dev/null || return 1
    fi
    printf 'Updated %s; backup saved to %s\n' "$file" "$backup"
}

fortify_update_local_hosts() {
    local ip="${1:-}" file="${FORTIFY_HOSTS_FILE:-/etc/hosts}" hosts current patched
    [ -n "$ip" ] || ip=$(fortify_lab_node_ip)
    hosts=$(fortify_lab_hostnames_inline)
    if [ -z "$ip" ]; then
        printf 'Could not determine the lab node IP for /etc/hosts. Enter it manually.\n' >&2
        return 1
    fi
    current=$(cat "$file" 2>/dev/null) || {
        printf 'Could not read %s.\n' "$file" >&2
        return 1
    }
    patched=$(printf '%s\n' "$current" | fortify_patch_local_hosts_file "$ip" "$hosts")
    if [ "$patched" = "$current" ]; then
        printf '%s already contains the current FortifyLab hosts block.\n' "$file"
        return 0
    fi
    fortify_local_hosts_apply_file "$file" "$patched"
}

fortify_remove_local_hosts() {
    local file="${FORTIFY_HOSTS_FILE:-/etc/hosts}" current patched
    current=$(cat "$file" 2>/dev/null) || {
        printf 'Could not read %s.\n' "$file" >&2
        return 1
    }
    patched=$(printf '%s\n' "$current" | fortify_remove_local_hosts_block)
    if [ "$patched" = "$current" ]; then
        printf '%s does not contain a FortifyLab hosts block.\n' "$file"
        return 0
    fi
    fortify_local_hosts_apply_file "$file" "$patched"
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
            if (hosts_block ~ /(ssc|sast|dast|lim|dashboard|juice-shop|webgoat|dvwa)\./) {
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
