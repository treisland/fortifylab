#!/bin/bash
# Read-only, offline Help Center for the Fortify Lab wizard.

# Stable topic IDs are a public wizard contract. Keep aliases below when an ID is
# superseded; released wizards and copied support instructions may still use it.
HELP_TOPIC_ID=(
    overview architecture ssc sast dast lim mysql postgresql dashboard roles glossary urls lab-scope
    guided/prerequisites guided/inputs guided/preflight guided/tls guided/dashboard guided/secrets
    guided/mysql guided/postgresql guided/ssc guided/lim guided/sast guided/dast guided/configuration
    troubleshooting/deployment troubleshooting/pending-pods troubleshooting/restarting-pods
    troubleshooting/url troubleshooting/tls troubleshooting/database troubleshooting/ssc
    troubleshooting/sast troubleshooting/dast troubleshooting/dashboard troubleshooting/license
    troubleshooting/registry
)
HELP_TOPIC_LABEL=(
    "System overview" "Dependencies and data flow" "Software Security Center (SSC)"
    "ScanCentral SAST" "ScanCentral DAST" "License and Infrastructure Manager (LIM)"
    "MySQL" "PostgreSQL" "Kubernetes Dashboard" "Roles and learning paths"
    "Glossary" "URLs and interfaces" "Lab deployment vs Fortify products"
)
HELP_TOPIC_FILE=(
    overview.txt architecture.txt ssc.txt sast.txt dast.txt lim.txt mysql.txt
    postgresql.txt dashboard.txt roles.txt glossary.txt urls.txt lab-scope.txt
    overview.txt overview.txt overview.txt urls.txt dashboard.txt overview.txt
    mysql.txt postgresql.txt ssc.txt lim.txt sast.txt dast.txt urls.txt
    overview.txt architecture.txt architecture.txt urls.txt urls.txt architecture.txt ssc.txt
    sast.txt dast.txt dashboard.txt lab-scope.txt architecture.txt
)
HELP_TOPIC_ROUTE=(
    index.html fortify/architecture-and-flows/ fortify/ssc/ fortify/scancentral-sast/
    fortify/scancentral-dast/ fortify/lim/ fortify/mysql/ fortify/postgresql/
    fortify/kubernetes-dashboard/ fortify/ fortify/ operations/networking-and-tls/ safety/
    getting-started/ getting-started/#1-clone-and-prepare-configuration getting-started/#2-start-fortify-lab
    operations/networking-and-tls/ fortify/kubernetes-dashboard/ operations/secrets-and-licenses/
    fortify/mysql/ fortify/postgresql/ fortify/ssc/ fortify/lim/ fortify/scancentral-sast/
    fortify/scancentral-dast/ operations/deployment-and-lifecycle/
    operations/troubleshooting/ operations/troubleshooting/#pods-remain-pending
    operations/troubleshooting/#pods-restart-or-never-become-ready operations/troubleshooting/#dns-ingress-urls-and-tls
    operations/troubleshooting/#dns-ingress-urls-and-tls operations/troubleshooting/#mysql-and-ssc
    operations/troubleshooting/#mysql-and-ssc operations/troubleshooting/#scancentral-sast
    operations/troubleshooting/#postgresql-lim-and-scancentral-dast operations/troubleshooting/#kubernetes-dashboard
    operations/secrets-and-licenses/ operations/troubleshooting/#image-pull-failures
)

help_topic_index() {
    local wanted="$1" index
    for index in "${!HELP_TOPIC_ID[@]}"; do
        [ "${HELP_TOPIC_ID[$index]}" = "$wanted" ] && { printf '%s\n' "$index"; return 0; }
    done
    return 1
}

help_guided_topic() {
    case "$1" in
        prereqs) printf '%s\n' guided/prerequisites ;;
        inputs) printf '%s\n' guided/inputs ;;
        preflight) printf '%s\n' guided/preflight ;;
        certs) printf '%s\n' guided/tls ;;
        dashboard|secrets|mysql|postgresql|ssc|lim|sast|dast) printf 'guided/%s\n' "$1" ;;
        sast_controller|sast_sensor) printf '%s\n' guided/sast ;;
        dast_core|dast_scanner) printf '%s\n' guided/dast ;;
        configure) printf '%s\n' guided/configuration ;;
        *) return 2 ;;
    esac
}

help_failure_topic() {
    case "$1" in
        failed-deploy) printf '%s\n' troubleshooting/deployment ;;
        pending-pods|restarting-pods|url|tls|database|ssc|sast|dast|dashboard|license|registry)
            printf 'troubleshooting/%s\n' "$1" ;;
        *) return 2 ;;
    esac
}

help_topic_online_url() {
    local topic="$1" index base
    index=$(help_topic_index "$topic") || return 2
    base="${FORTIFY_DOCS_BASE_URL:-https://treisland.github.io/fortifylab}"
    base="${base%/}"
    case "$base" in
        http://*|https://*) ;;
        *) error "FORTIFY_DOCS_BASE_URL must use http:// or https://"; return 2 ;;
    esac
    printf '%s/%s\n' "$base" "${HELP_TOPIC_ROUTE[$index]}"
}

help_render_topic() {
    local topic="$1" index file online_url
    index=$(help_topic_index "$topic") || {
        error "Unknown help topic: $topic"
        return 2
    }
    file="$FORTIFY_HOME_K8S/docs/help/${HELP_TOPIC_FILE[$index]}"
    title "Help — ${HELP_TOPIC_LABEL[$index]}"
    if [ ! -r "$file" ]; then
        error "Help document is unavailable: docs/help/${HELP_TOPIC_FILE[$index]}"
        echo "  Reinstall or restore the repository documentation, then try again."
        return 1
    fi
    printf '\n'
    sed 's/^/  /' "$file"
    if online_url=$(help_topic_online_url "$topic"); then
        printf '\n  Online topic: %s\n' "$online_url"
    else
        warning "Online documentation link is unavailable; offline help above is still valid."
    fi
}

help_print_topic_reference() {
    local topic="$1" index online_url
    index=$(help_topic_index "$topic") || return 2
    printf '  Help topic: %s (offline: docs/help/%s)\n' "$topic" "${HELP_TOPIC_FILE[$index]}"
    if online_url=$(help_topic_online_url "$topic"); then
        printf '  Online guide: %s\n' "$online_url"
    fi
}

help_show_topic() {
    help_render_topic "$1"
    press_any
}

help_center() {
    local choice index
    while true; do
        title "Help Center"
        cat <<'EOF'

  Offline, read-only guidance for understanding this Fortify lab.
  Viewing a help topic never queries or changes Kubernetes, files, or credentials.
  Reset acknowledgement is a separate, explicitly confirmed local action.

EOF
        for index in "${!HELP_TOPIC_LABEL[@]}"; do
            printf '  %2d. %s\n' "$((index + 1))" "${HELP_TOPIC_LABEL[$index]}"
        done
        echo
        echo "   l. View the lab/demo-use disclaimer"
        echo "   x. Reset lab-use acknowledgement"
        echo "   r. Return"
        echo
        ask choice "Select a topic:"
        case "$choice" in
            [Rr]) return ;;
            [Ll]) title "Lab / demo-use disclaimer"; fortify_lab_show_notice; press_any ;;
            [Xx])
                if confirm "Reset the saved lab-use acknowledgement?"; then
                    fortify_lab_reset_acknowledgement
                    press_any
                fi
                ;;
            ''|*[!0-9]*) error "Invalid selection"; sleep 1 ;;
            *)
                if [ "$choice" -ge 1 ] && [ "$choice" -le "${#HELP_TOPIC_ID[@]}" ]; then
                    help_show_topic "${HELP_TOPIC_ID[$((choice - 1))]}"
                else
                    error "Out of range"; sleep 1
                fi
                ;;
        esac
    done
}
