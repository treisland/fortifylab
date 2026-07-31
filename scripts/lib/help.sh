#!/bin/bash
# Read-only, offline Help Center for the Fortify Lab wizard.

HELP_TOPIC_ID=(overview architecture ssc sast dast lim mysql postgresql dashboard roles glossary urls lab-scope)
HELP_TOPIC_LABEL=(
    "System overview" "Dependencies and data flow" "Software Security Center (SSC)"
    "ScanCentral SAST" "ScanCentral DAST" "License and Infrastructure Manager (LIM)"
    "MySQL" "PostgreSQL" "Kubernetes Dashboard" "Roles and learning paths"
    "Glossary" "URLs and interfaces" "Lab deployment vs Fortify products"
)
HELP_TOPIC_FILE=(
    overview.txt architecture.txt ssc.txt sast.txt dast.txt lim.txt mysql.txt
    postgresql.txt dashboard.txt roles.txt glossary.txt urls.txt lab-scope.txt
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
        prereqs|inputs|preflight|certs|secrets) printf '%s\n' overview ;;
        dashboard) printf '%s\n' dashboard ;;
        mysql) printf '%s\n' mysql ;;
        postgresql) printf '%s\n' postgresql ;;
        ssc) printf '%s\n' ssc ;;
        lim) printf '%s\n' lim ;;
        sast) printf '%s\n' sast ;;
        dast) printf '%s\n' dast ;;
        configure) printf '%s\n' urls ;;
        *) printf '%s\n' overview ;;
    esac
}

help_render_topic() {
    local topic="$1" index file
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
