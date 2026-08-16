#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# Runbook Library
# ============================================================

RUNBOOK_ROOT_DIR="${RUNBOOK_ROOT_DIR:-$FORTIFY_HOME_K8S/runbooks}"
RUNBOOK_SELECTED_PARAM_VALUES=()
RUNBOOK_PARAM_NAMES=()
RUNBOOK_PARAM_DESCRIPTIONS=()
RUNBOOK_PARAM_DEFAULTS=()
RUNBOOK_PARAM_DEFAULT_FROM_ENV=()
RUNBOOK_PARAM_REQUIRED=()
RUNBOOK_PARSE_ERRORS=()
RUNBOOK_NAME=""
RUNBOOK_DESCRIPTION=""
RUNBOOK_CATEGORY="General"
RUNBOOK_DOMAIN="General"
RUNBOOK_RISK=""
RUNBOOK_ORDER="1000"
RUNBOOK_REQUIRES=""
RUNBOOK_TYPE="script"
TAB=$'\t'
RUNBOOK_MARKER=""

runbook_source_label_for_path() {
    local path="$1" rel
    rel="${path#$RUNBOOK_ROOT_DIR/}"
    case "$rel" in
        official/*) printf '%s\n' "Official" ;;
        training/*) printf '%s\n' "Training" ;;
        local/*) printf '%s\n' "Local" ;;
        *) printf '%s\n' "Custom" ;;
    esac
}

runbook_source_rank_for_label() {
    case "$1" in
        Official) printf '%s\n' 1 ;;
        Training) printf '%s\n' 2 ;;
        Local) printf '%s\n' 3 ;;
        *) printf '%s\n' 4 ;;
    esac
}

runbook_trim() {
    local value="$*"
    value="${value#${value%%[![:space:]]*}}"
    value="${value%${value##*[![:space:]]}}"
    printf '%s\n' "$value"
}

runbook_env_name() {
    local name="$1" upper
    upper="$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')"
    printf '%s\n' "$upper" | sed 's/[^A-Z0-9_]/_/g'
}

runbook_reset_metadata() {
    RUNBOOK_SELECTED_PARAM_VALUES=()
    RUNBOOK_PARAM_NAMES=()
    RUNBOOK_PARAM_DESCRIPTIONS=()
    RUNBOOK_PARAM_DEFAULTS=()
    RUNBOOK_PARAM_DEFAULT_FROM_ENV=()
    RUNBOOK_PARAM_REQUIRED=()
    RUNBOOK_PARSE_ERRORS=()
    RUNBOOK_NAME=""
    RUNBOOK_DESCRIPTION=""
    RUNBOOK_CATEGORY="General"
    RUNBOOK_DOMAIN="General"
    RUNBOOK_RISK=""
    RUNBOOK_ORDER="1000"
    RUNBOOK_REQUIRES=""
    RUNBOOK_TYPE="script"
    RUNBOOK_MARKER=""
}

runbook_metadata_set() {
    local key="$1" value="$2"
    case "$key" in
        fortifylab-runbook) RUNBOOK_MARKER="$value" ;;
        name) RUNBOOK_NAME="$value" ;;
        description) RUNBOOK_DESCRIPTION="$value" ;;
        category) RUNBOOK_CATEGORY="$value" ;;
        domain) RUNBOOK_DOMAIN="$value" ;;
        risk) RUNBOOK_RISK="$value" ;;
        order) RUNBOOK_ORDER="$value" ;;
        requires) RUNBOOK_REQUIRES="$value" ;;
        type) RUNBOOK_TYPE="$value" ;;
    esac
}

runbook_param_set() {
    local index="$1" key="$2" value="$3"
    case "$key" in
        name) RUNBOOK_PARAM_NAMES[$index]="$value" ;;
        description) RUNBOOK_PARAM_DESCRIPTIONS[$index]="$value" ;;
        default) RUNBOOK_PARAM_DEFAULTS[$index]="$value" ;;
        defaultFromEnv) RUNBOOK_PARAM_DEFAULT_FROM_ENV[$index]="$value" ;;
        required) RUNBOOK_PARAM_REQUIRED[$index]="$value" ;;
    esac
}

runbook_parse_file() {
    local file="$1" line meta key value param_index=-1 param_key param_value
    runbook_reset_metadata
    [ -f "$file" ] || { RUNBOOK_PARSE_ERRORS+=("file does not exist"); return 1; }
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] || continue
        meta="${line#*#}"
        meta="$(runbook_trim "$meta")"
        [ -n "$meta" ] || continue
        if [[ "$meta" =~ ^-[[:space:]]name:[[:space:]]*(.*)$ ]]; then
            param_index=$((param_index + 1))
            runbook_param_set "$param_index" name "$(runbook_trim "${BASH_REMATCH[1]}")"
            continue
        fi
        if [[ "$meta" =~ ^-[[:space:]]([A-Za-z][A-Za-z0-9_-]*):[[:space:]]*(.*)$ ]]; then
            param_index=$((param_index + 1))
            runbook_param_set "$param_index" "${BASH_REMATCH[1]}" "$(runbook_trim "${BASH_REMATCH[2]}")"
            continue
        fi
        if [[ "$meta" =~ ^([A-Za-z][A-Za-z0-9_-]*):[[:space:]]*(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            value="$(runbook_trim "${BASH_REMATCH[2]}")"
            if [ "$param_index" -ge 0 ] && [[ "$key" =~ ^(description|default|defaultFromEnv|required)$ ]]; then
                runbook_param_set "$param_index" "$key" "$value"
            else
                runbook_metadata_set "$key" "$value"
            fi
        fi
    done < "$file"
}

runbook_is_risk_valid() {
    case "$1" in
        low|medium|high|destructive) return 0 ;;
        *) return 1 ;;
    esac
}

runbook_is_order_valid() {
    [[ "${1:-}" =~ ^[0-9]+$ ]]
}

runbook_is_param_name_valid() {
    [[ "${1:-}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]
}

runbook_required_tools_missing() {
    local requires="$1" tool missing=() normalized
    normalized="${requires//,/ }"
    for tool in $normalized; do
        [ -z "$tool" ] && continue
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
    [ ${#missing[@]} -eq 0 ] && return 0
    printf '%s\n' "${missing[*]}"
    return 1
}

runbook_validate_current_metadata() {
    local file="$1" idx name missing_tools
    [ "$RUNBOOK_MARKER" = "true" ] || RUNBOOK_PARSE_ERRORS+=("missing metadata marker: fortifylab-runbook: true")
    [ -n "$RUNBOOK_NAME" ] || RUNBOOK_PARSE_ERRORS+=("missing required metadata: name")
    [ -n "$RUNBOOK_DESCRIPTION" ] || RUNBOOK_PARSE_ERRORS+=("missing required metadata: description")
    [ -n "$RUNBOOK_RISK" ] || RUNBOOK_PARSE_ERRORS+=("missing required metadata: risk")
    if [ -n "$RUNBOOK_RISK" ] && ! runbook_is_risk_valid "$RUNBOOK_RISK"; then
        RUNBOOK_PARSE_ERRORS+=("invalid risk '$RUNBOOK_RISK'; use low, medium, high, or destructive")
    fi
    if ! runbook_is_order_valid "$RUNBOOK_ORDER"; then
        RUNBOOK_PARSE_ERRORS+=("invalid order '$RUNBOOK_ORDER'; use a number")
    fi
    for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
        name="${RUNBOOK_PARAM_NAMES[$idx]}"
        if ! runbook_is_param_name_valid "$name"; then
            RUNBOOK_PARSE_ERRORS+=("invalid parameter name '$name'; use letters, numbers, and underscores")
        fi
    done
    if [ -n "$RUNBOOK_REQUIRES" ]; then
        missing_tools="$(runbook_required_tools_missing "$RUNBOOK_REQUIRES" 2>/dev/null || true)"
        [ -z "$missing_tools" ] || RUNBOOK_PARSE_ERRORS+=("missing required tools: $missing_tools")
    fi
    bash -n "$file" >/dev/null 2>&1 || RUNBOOK_PARSE_ERRORS+=("script failed bash syntax validation")
    [ ${#RUNBOOK_PARSE_ERRORS[@]} -eq 0 ]
}

runbook_validate_file() {
    local file="$1"
    runbook_parse_file "$file"
    runbook_validate_current_metadata "$file"
}

runbook_discover_files() {
    local dir
    for dir in "$RUNBOOK_ROOT_DIR/official" "$RUNBOOK_ROOT_DIR/training" "$RUNBOOK_ROOT_DIR/local"; do
        [ -d "$dir" ] || continue
        find "$dir" -type f -name '*.sh' | sort
    done
}

runbook_discover_records() {
    local file source rank name domain category risk order description
    while IFS= read -r file; do
        [ -n "$file" ] || continue
        runbook_parse_file "$file"
        [ "$RUNBOOK_MARKER" = "true" ] || continue
        source="$(runbook_source_label_for_path "$file")"
        rank="$(runbook_source_rank_for_label "$source")"
        name="${RUNBOOK_NAME:-$(basename "$file")}" domain="${RUNBOOK_DOMAIN:-General}" category="${RUNBOOK_CATEGORY:-General}"
        risk="${RUNBOOK_RISK:-unknown}" order="${RUNBOOK_ORDER:-1000}" description="$RUNBOOK_DESCRIPTION"
        printf '%s\t%s\t%06d\t%s\t%s\t%s\t%s\t%s\t%s\n' "$rank" "$source" "$order" "$domain" "$category" "$name" "$risk" "$file" "$description"
    done < <(runbook_discover_files) | sort -t "$TAB" -k4,4f -k1,1n -k5,5f -k3,3n -k6,6f -k8,8f
}

runbook_param_default_value() {
    local idx="$1" env_key value
    env_key="${RUNBOOK_PARAM_DEFAULT_FROM_ENV[$idx]:-}"
    if [ -n "$env_key" ]; then
        value="${!env_key:-}"
        [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    fi
    printf '%s\n' "${RUNBOOK_PARAM_DEFAULTS[$idx]:-}"
}

runbook_param_value() {
    local idx="$1"
    if [ "${RUNBOOK_SELECTED_PARAM_VALUES[$idx]+set}" = set ]; then
        printf '%s\n' "${RUNBOOK_SELECTED_PARAM_VALUES[$idx]}"
    else
        runbook_param_default_value "$idx"
    fi
}

runbook_param_is_secret() {
    local name="${1:-}"
    [[ "$name" =~ (pass|password|token|secret|key|credential) ]]
}

runbook_param_display_value() {
    local idx="$1" name value
    name="${RUNBOOK_PARAM_NAMES[$idx]:-}"
    value="$(runbook_param_value "$idx")"
    if runbook_param_is_secret "$name"; then
        [ -n "$value" ] && printf '%s\n' "<redacted>" || printf '%s\n' "<unset>"
    else
        [ -n "$value" ] && printf '%s\n' "$value" || printf '%s\n' "<unset>"
    fi
}

runbook_init_param_values() {
    local idx
    RUNBOOK_SELECTED_PARAM_VALUES=()
    for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
        RUNBOOK_SELECTED_PARAM_VALUES[$idx]="$(runbook_param_default_value "$idx")"
    done
}

runbook_required_params_missing() {
    local idx required value missing=()
    for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
        required="${RUNBOOK_PARAM_REQUIRED[$idx]:-false}"
        value="$(runbook_param_value "$idx")"
        if [[ "$required" =~ ^(true|yes|1)$ ]] && [ -z "$value" ]; then
            missing+=("${RUNBOOK_PARAM_NAMES[$idx]}")
        fi
    done
    [ ${#missing[@]} -eq 0 ] && return 0
    printf '%s\n' "${missing[*]}"
    return 1
}

runbook_print_metadata() {
    local file="$1" source missing_tools
    source="$(runbook_source_label_for_path "$file")"
    printf 'Domain:   %s\n' "${RUNBOOK_DOMAIN:-General}"
    printf 'Category: %s\n' "${RUNBOOK_CATEGORY:-General}"
    printf 'Risk:     %s\n' "${RUNBOOK_RISK:-unknown}"
    printf 'Type:     %s\n' "${RUNBOOK_TYPE:-script}"
    printf 'Source:   %s\n' "$source"
    printf 'Path:     %s\n' "${file#$FORTIFY_HOME_K8S/}"
    if [ -n "$RUNBOOK_REQUIRES" ]; then
        missing_tools="$(runbook_required_tools_missing "$RUNBOOK_REQUIRES" 2>/dev/null || true)"
        if [ -n "$missing_tools" ]; then
            printf 'Requires: %s (%smissing: %s%s)\n' "$RUNBOOK_REQUIRES" "$YELLOW" "$missing_tools" "$RESET"
        else
            printf 'Requires: %s\n' "$RUNBOOK_REQUIRES"
        fi
    fi
    printf '\n%s\n' "$RUNBOOK_DESCRIPTION"
}

runbook_print_params() {
    local idx name value required suffix
    if [ ${#RUNBOOK_PARAM_NAMES[@]} -eq 0 ]; then
        printf '  %s\n' "No parameters."
        return
    fi
    for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
        name="${RUNBOOK_PARAM_NAMES[$idx]}"
        value="$(runbook_param_display_value "$idx")"
        required="${RUNBOOK_PARAM_REQUIRED[$idx]:-false}"
        suffix=""
        [[ "$required" =~ ^(true|yes|1)$ ]] && suffix=" required"
        printf '  %2d. %-22s %s%s\n' "$((idx + 1))" "$name" "$value" "$suffix"
        [ -z "${RUNBOOK_PARAM_DESCRIPTIONS[$idx]:-}" ] || printf '      %s\n' "${RUNBOOK_PARAM_DESCRIPTIONS[$idx]}"
    done
}

runbook_preview_script() {
    local file="$1"
    title "Runbook script preview"
    printf 'Path: %s\n\n' "${file#$FORTIFY_HOME_K8S/}"
    sed -n '1,220p' "$file"
    press_any
}

runbook_show_resolved_command() {
    local file="$1" idx name env_name value
    title "Runbook command preview"
    printf 'Runbook: %s\n\n' "$RUNBOOK_NAME"
    for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
        name="${RUNBOOK_PARAM_NAMES[$idx]}"
        env_name="$(runbook_env_name "$name")"
        if runbook_param_is_secret "$name"; then
            printf '%s=<redacted>\n' "$env_name"
        else
            value="$(runbook_param_value "$idx")"
            printf '%s=%q\n' "$env_name" "$value"
        fi
    done
    printf 'bash %q\n' "${file#$FORTIFY_HOME_K8S/}"
    press_any
}

runbook_edit_params() {
    local choice idx name current value
    if [ ${#RUNBOOK_PARAM_NAMES[@]} -eq 0 ]; then
        note "This runbook does not declare parameters."
        press_any
        return 0
    fi
    while true; do
        title "Edit runbook parameters"
        runbook_print_params
        echo
        echo "   b. Back"
        echo
        ask choice "Select parameter:"
        case "$choice" in
            [Bb]) return 0 ;;
            ''|*[!0-9]*) error "Select a parameter number."; sleep 1 ;;
            *)
                idx=$((choice - 1))
                if [ "$idx" -lt 0 ] || [ "$idx" -ge "${#RUNBOOK_PARAM_NAMES[@]}" ]; then
                    error "Select a parameter number shown above."
                    sleep 1
                    continue
                fi
                name="${RUNBOOK_PARAM_NAMES[$idx]}"
                current="$(runbook_param_value "$idx")"
                if runbook_param_is_secret "$name"; then
                    read -rsp "$name [<redacted>]: " value
                    echo
                else
                    read -rp "$name [$current]: " value
                fi
                [ -n "$value" ] || value="$current"
                RUNBOOK_SELECTED_PARAM_VALUES[$idx]="$value"
                ;;
        esac
    done
}

runbook_validate_screen() {
    local file="$1" idx
    title "Validate runbook"
    runbook_parse_file "$file"
    if runbook_validate_current_metadata "$file"; then
        printf '%s Metadata and script checks passed.\n' "$OK_MARK"
    else
        printf '%s Runbook has issues:\n' "$FAIL_MARK"
        for idx in "${!RUNBOOK_PARSE_ERRORS[@]}"; do
            printf '  - %s\n' "${RUNBOOK_PARSE_ERRORS[$idx]}"
        done
    fi
    press_any
}

runbook_validate_all() {
    local file count=0 failed=0 idx
    title "Validate runbooks"
    while IFS= read -r file; do
        [ -n "$file" ] || continue
        count=$((count + 1))
        runbook_parse_file "$file"
        if runbook_validate_current_metadata "$file"; then
            printf '%s %s\n' "$OK_MARK" "${file#$FORTIFY_HOME_K8S/}"
        else
            failed=$((failed + 1))
            printf '%s %s\n' "$FAIL_MARK" "${file#$FORTIFY_HOME_K8S/}"
            for idx in "${!RUNBOOK_PARSE_ERRORS[@]}"; do
                printf '    - %s\n' "${RUNBOOK_PARSE_ERRORS[$idx]}"
            done
        fi
    done < <(runbook_discover_files)
    [ "$count" -gt 0 ] || note "No runbook scripts found under $RUNBOOK_ROOT_DIR."
    echo
    if [ "$failed" -eq 0 ]; then
        note "Validated $count runbook script(s)."
    else
        error "$failed of $count runbook script(s) need attention."
    fi
    press_any
}

runbook_confirm_risk() {
    case "$RUNBOOK_RISK" in
        high|destructive)
            printf '%s This runbook is marked %s. Review the preview before running.\n' "$WARN_MARK" "$RUNBOOK_RISK"
            confirm "Run $RUNBOOK_NAME?"
            ;;
        *) return 0 ;;
    esac
}


runbook_redact_output() {
    sed -E \
        -e 's/([Pp]assword[[:space:]_=-]*)([^[:space:]]+)/\1<redacted>/g' \
        -e 's/([Tt]oken[[:space:]_=-]*)([^[:space:]]+)/\1<redacted>/g' \
        -e 's/([Ss]ecret[[:space:]_=-]*)([^[:space:]]+)/\1<redacted>/g' \
        -e 's/(SSC_CI_TOKEN[[:space:]_=-]*)([^[:space:]]+)/\1<redacted>/g'
}

runbook_run() {
    local file="$1" missing idx name env_name value rel log_file rc
    local selected_values=()
    selected_values=("${RUNBOOK_SELECTED_PARAM_VALUES[@]}")
    runbook_validate_file "$file" || { runbook_validate_screen "$file"; return 1; }
    if [ ${#selected_values[@]} -gt 0 ]; then
        RUNBOOK_SELECTED_PARAM_VALUES=("${selected_values[@]}")
    else
        runbook_init_param_values
    fi
    missing="$(runbook_required_params_missing 2>/dev/null || true)"
    if [ -n "$missing" ]; then
        error "Required parameter value missing: $missing"
        runbook_edit_params
        missing="$(runbook_required_params_missing 2>/dev/null || true)"
        [ -z "$missing" ] || { error "Required parameter value missing: $missing"; press_any; return 1; }
    fi
    runbook_confirm_risk || return 1
    title "Runbook output"
    rel="${file#$FORTIFY_HOME_K8S/}"
    note "Running $RUNBOOK_NAME ($rel)"
    wizard_log_event "action=runbook_start name=$(printf '%q' "$RUNBOOK_NAME") path=$(printf '%q' "$rel") risk=${RUNBOOK_RISK:-unknown}"
    fortify_wizard_log_prepare >/dev/null 2>&1 || true
    log_file="$(fortify_wizard_log_file 2>/dev/null || true)"
    if [ -z "$log_file" ]; then
        (
            cd "$FORTIFY_HOME_K8S" || exit 1
            for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
                name="${RUNBOOK_PARAM_NAMES[$idx]}"
                env_name="$(runbook_env_name "$name")"
                value="$(runbook_param_value "$idx")"
                export "$env_name=$value"
            done
            bash "$file"
        ) 2>&1 | runbook_redact_output
        rc=${PIPESTATUS[0]}
    else
        (
            cd "$FORTIFY_HOME_K8S" || exit 1
            for idx in "${!RUNBOOK_PARAM_NAMES[@]}"; do
                name="${RUNBOOK_PARAM_NAMES[$idx]}"
                env_name="$(runbook_env_name "$name")"
                value="$(runbook_param_value "$idx")"
                export "$env_name=$value"
            done
            bash "$file"
        ) 2>&1 | runbook_redact_output | tee -a "$log_file"
        rc=${PIPESTATUS[0]}
    fi
    if [ "$rc" -eq 0 ]; then
        note "Runbook completed successfully."
        wizard_log_event "action=runbook_complete name=$(printf '%q' "$RUNBOOK_NAME") state=success"
    else
        error "Runbook failed with exit code $rc."
        wizard_log_event "action=runbook_complete name=$(printf '%q' "$RUNBOOK_NAME") state=failed exit_code=$rc"
    fi
    press_any
    return "$rc"
}

runbook_detail_menu() {
    local file="$1" choice
    runbook_parse_file "$file"
    runbook_init_param_values
    while true; do
        title "$RUNBOOK_NAME"
        runbook_print_metadata "$file"
        section "Parameters"
        runbook_print_params
        section "Actions"
        echo "   1. Run"
        echo "   2. Edit parameters"
        echo "   3. Preview script"
        echo "   4. Show resolved command"
        echo "   5. Validate this runbook"
        echo
        echo "   b. Back"
        echo "   q. Quit"
        echo
        ask choice "Select:"
        case "$choice" in
            1) runbook_run "$file" ;;
            2) runbook_edit_params ;;
            3) runbook_preview_script "$file" ;;
            4) runbook_show_resolved_command "$file" ;;
            5) runbook_validate_screen "$file" ;;
            [Bb]) return 0 ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid choice"; sleep 1 ;;
        esac
    done
}

runbook_authoring_help() {
    title "Runbook authoring"
    cat <<EOF
Runbooks are Bash scripts with metadata comments. Copy the template, edit it in
VS Code, Notepad++, or your preferred editor, then validate from this menu.

Template:
  runbooks/templates/shell-runbook.sh

Shared folders:
  runbooks/official   maintained FortifyLab runbooks
  runbooks/training   classroom, demo, and workshop runbooks
  runbooks/local      private local scripts ignored by git

Required metadata:
  fortifylab-runbook: true
  name
  description
  risk: low | medium | high | destructive

Parameters are optional. Parameter names become uppercase environment variables
when the script runs. For example app_name becomes APP_NAME.
EOF
    press_any
}

runbook_domain_menu() {
    local selected_domain="$1" records=() files=() record choice number=0 rank source order domain category name risk file description last_source="" last_category=""
    while true; do
        files=(); number=0; last_source=""; last_category=""
        title "$selected_domain Runbooks"
        while IFS= read -r record; do
            [ -n "$record" ] || continue
            IFS="$TAB" read -r rank source order domain category name risk file description <<< "$record"
            [ "$domain" = "$selected_domain" ] || continue
            if [ "$source" != "$last_source" ]; then
                section "$source runbooks"
                last_source="$source"
                last_category=""
            fi
            if [ "$category" != "$last_category" ]; then
                printf '  %s\n' "$category"
                last_category="$category"
            fi
            number=$((number + 1))
            files[$number]="$file"
            printf '    %2d. %-34s %s%s%s\n' "$number" "$name" "$DIM" "$risk" "$RESET"
        done < <(runbook_discover_records)
        [ "$number" -gt 0 ] || note "No runbooks found for $selected_domain."
        echo
        echo "   b. Back"
        echo "   q. Quit"
        echo
        ask choice "Select a runbook:"
        case "$choice" in
            [Bb]) return 0 ;;
            [Qq]) clear; exit 0 ;;
            ''|*[!0-9]*) error "Select a runbook number shown above."; sleep 1 ;;
            *)
                if [ "$choice" -lt 1 ] || [ "$choice" -gt "$number" ]; then
                    error "Select a runbook number shown above."
                    sleep 1
                else
                    runbook_detail_menu "${files[$choice]}"
                fi
                ;;
        esac
    done
}

runbooks_menu() {
    local domains=() counts=() record choice rank source order domain category name risk file description idx found
    while true; do
        domains=(); counts=()
        title "Runbook Library"
        cat <<'EOF'
Reusable scripts for demos, fixes, diagnostics, and customer workflows.
Choose a domain first so local SSC, ScanCentral, FoD, CI/CD, and private runbooks stay separate.
EOF
        echo
        while IFS= read -r record; do
            [ -n "$record" ] || continue
            IFS="$TAB" read -r rank source order domain category name risk file description <<< "$record"
            found=0
            for idx in "${!domains[@]}"; do
                if [ "${domains[$idx]}" = "$domain" ]; then
                    counts[$idx]=$((counts[$idx] + 1))
                    found=1
                    break
                fi
            done
            if [ "$found" -eq 0 ]; then
                domains+=("$domain")
                counts+=(1)
            fi
        done < <(runbook_discover_records)
        if [ "${#domains[@]}" -eq 0 ]; then
            note "No runbooks found. Copy the template into runbooks/local or runbooks/training to get started."
        else
            section "Runbook domains"
            for idx in "${!domains[@]}"; do
                printf '  %2d. %-34s %s%d runbook(s)%s\n' "$((idx + 1))" "${domains[$idx]}" "$DIM" "${counts[$idx]}" "$RESET"
            done
        fi
        echo
        echo "   v. Validate runbooks"
        echo "   t. Templates and authoring help"
        echo "   b. Back"
        echo "   q. Quit"
        echo
        ask choice "Select a domain:"
        case "$choice" in
            [Vv]) runbook_validate_all ;;
            [Tt]) runbook_authoring_help ;;
            [Bb]) return 0 ;;
            [Qq]) clear; exit 0 ;;
            ''|*[!0-9]*) error "Select a domain number shown above."; sleep 1 ;;
            *)
                if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#domains[@]}" ]; then
                    error "Select a domain number shown above."
                    sleep 1
                else
                    runbook_domain_menu "${domains[$((choice - 1))]}"
                fi
                ;;
        esac
    done
}
