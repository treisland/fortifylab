#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/environment-store
# Responsibility: Read, redact, back up, update, and restore wizard environment files.
# Requires: FORTIFY_HOME_K8S; ENV_FILE; ENV_BACKUP_DIR; ENV_LAST_BACKUP and
#           ENV_LAST_BACKUP_META (written); error, note, section, ask, press_any,
#           wizard_log_event; Python config CLI (optional).
# Exports: env_is_secret_key, python_config_available, python_config_diagnostics,
#          python_config_validate, python_config_repair_domain_urls, env_display_value,
#          env_shell_quote, env_assignment_expr, env_prepare_backup, env_current_value,
#          env_apply_updates, env_preview_changes, env_backup_files, env_restore_backup,
#          env_rollback_last, env_restore_selected, env_pending_value,
#          env_pending_has_key, env_pending_set.
# Side effects: Reads and writes ENV_FILE and its backup files.
# Interactive: env_rollback_last and env_restore_selected may prompt.

if [[ -n "${FORTIFYLAB_WIZARD_ENVIRONMENT_STORE_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_ENVIRONMENT_STORE_LOADED=1

env_is_secret_key() {
    case "$1" in
        *PASS*|*PASSWORD*|*TOKEN*|*SECRET*|*KEY*|*LICENSE*|*CREDENTIAL*) return 0 ;;
        *) return 1 ;;
    esac
}

python_config_available() {
    command -v python3 >/dev/null 2>&1 &&
        [ -x "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" ] &&
        [ -s "${ENV_FILE:-}" ]
}

python_config_diagnostics() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config diagnostics --env "$ENV_FILE"
}

python_config_validate() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config validate --env "$ENV_FILE"
}

python_config_repair_domain_urls() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config repair-derived --env "$ENV_FILE" --apply
}

env_display_value() {
    local key="$1" value="${2:-}"
    if env_is_secret_key "$key"; then
        [ -n "$value" ] && printf '%s\n' '<redacted>' || printf '%s\n' '<unset>'
    else
        printf '%s\n' "${value:-<unset>}"
    fi
}

env_shell_quote() {
    local value="$1"
    printf "'%s'" "${value//\'/\'\\\'\'}"
}

env_assignment_expr() {
    local key="$1" value="$2" mode="${3:-literal}"
    if [ "$mode" = expr ]; then
        printf 'export %s="%s"' "$key" "$value"
    else
        printf 'export %s=%s' "$key" "$(env_shell_quote "$value")"
    fi
}

env_backup_timestamp() { date +%Y%m%d-%H%M%S; }

env_prepare_backup() {
    local reason="${1:-wizard-edit}" timestamp backup meta
    timestamp=$(env_backup_timestamp)
    mkdir -p "$ENV_BACKUP_DIR" || return 1
    backup="$ENV_BACKUP_DIR/.env.$timestamp.$reason.bak"
    meta="$ENV_BACKUP_DIR/.env.$timestamp.$reason.meta"
    cp "$ENV_FILE" "$backup" || return 1
    ENV_LAST_BACKUP="$backup"
    ENV_LAST_BACKUP_META="$meta"
    printf 'created_by=fortifylab-wizard\ncreated_at=%s\nreason=%s\n' "$timestamp" "$reason" >"$meta"
    printf '%s\n' "$backup" >"$FORTIFY_HOME_K8S/.env.rollback"
}

env_current_value() {
    local key="$1"
    ( set -a; source "$ENV_FILE" >/dev/null 2>&1; printf '%s\n' "${!key:-}" )
}

env_apply_updates() {
    local reason="$1" key value mode pair changed_keys=() tmp line
    shift
    [ -s "$ENV_FILE" ] || { error "$ENV_FILE does not exist or is empty."; return 1; }
    [ "$#" -gt 0 ] || { note "No changes selected."; return 0; }
    env_prepare_backup "$reason" || { error "Could not create .env backup."; return 1; }
    tmp="$FORTIFY_HOME_K8S/.env.tmp"
    cp "$ENV_FILE" "$tmp" || return 1
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        mode=literal
        case "$value" in
            __EXPR__*) mode=expr; value="${value#__EXPR__}" ;;
        esac
        line=$(env_assignment_expr "$key" "$value" "$mode")
        awk -v key="$key" -v newline="$line" '
            BEGIN { replaced = 0 }
            $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "=" { print newline; replaced = 1; next }
            { print }
            END { if (!replaced) { print ""; print newline } }
        ' "$tmp" >"$tmp.next" || return 1
        mv "$tmp.next" "$tmp" || return 1
        changed_keys+=("$key")
    done
    mv "$tmp" "$ENV_FILE" || return 1
    {
        printf 'changed_keys='
        local sep=""
        for key in "${changed_keys[@]}"; do
            printf '%s%s' "$sep" "$key"
            sep=,
        done
        printf '\n'
    } >>"$ENV_LAST_BACKUP_META"
    wizard_log_event "action=env_update reason=$reason backup=$(basename "$ENV_LAST_BACKUP") keys=${changed_keys[*]}"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    note "Updated .env. Backup: $ENV_LAST_BACKUP"
    section "Changed keys"
    for key in "${changed_keys[@]}"; do
        printf '  - %s\n' "$key"
    done
}

env_preview_changes() {
    local key new mode old display_old display_new pair
    for pair in "$@"; do
        key="${pair%%=*}"
        new="${pair#*=}"
        mode=literal
        case "$new" in
            __EXPR__*) mode=expr; new="${new#__EXPR__}" ;;
        esac
        old=$(env_current_value "$key")
        if [ "$mode" = expr ]; then
            display_new="$new"
        else
            display_new="$new"
        fi
        display_old=$(env_display_value "$key" "$old")
        display_new=$(env_display_value "$key" "$display_new")
        printf '  %-32s %s -> %s\n' "$key" "$display_old" "$display_new"
    done
}

env_backup_files() {
    find "$ENV_BACKUP_DIR" -maxdepth 1 -type f -name '.env.*.bak' 2>/dev/null | sort -r
}

env_restore_backup() {
    local backup="$1" reason="${2:-restore}"
    [ -s "$backup" ] || { error "Backup not found: $backup"; return 1; }
    env_prepare_backup "before-$reason" || return 1
    cp "$backup" "$ENV_FILE" || return 1
    wizard_log_event "action=env_restore restored=$(basename "$backup") rollback=$(basename "$ENV_LAST_BACKUP")"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    note "Restored .env from $backup"
}

env_rollback_last() {
    local backup
    if [ -s "$FORTIFY_HOME_K8S/.env.rollback" ]; then
        backup=$(cat "$FORTIFY_HOME_K8S/.env.rollback")
    else
        backup=$(env_backup_files | head -n 1)
    fi
    [ -n "${backup:-}" ] || { error "No .env backups are available."; return 1; }
    env_restore_backup "$backup" rollback-last
}

env_restore_selected() {
    local backups=() choice idx
    while IFS= read -r choice; do backups+=("$choice"); done < <(env_backup_files)
    [ "${#backups[@]}" -gt 0 ] || { error "No .env backups are available."; press_any; return 1; }
    section "Available .env backups"
    for idx in "${!backups[@]}"; do
        printf '  %d. %s\n' $((idx + 1)) "${backups[$idx]}"
    done
    echo
    ask choice "Restore which backup number (or empty to cancel):"
    [ -z "$choice" ] && return 0
    [[ "$choice" =~ ^[0-9]+$ ]] || { error "Invalid selection"; return 1; }
    [ "$choice" -ge 1 ] && [ "$choice" -le "${#backups[@]}" ] || { error "Out of range"; return 1; }
    env_restore_backup "${backups[$((choice - 1))]}" restore-selected
}

env_pending_value() {
    local key="$1" fallback="${2:-}" pair
    shift 2 || true
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] || continue
        printf '%s\n' "${pair#*=}"
        return 0
    done
    printf '%s\n' "$fallback"
}

env_pending_has_key() {
    local key="$1" pair
    shift
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] && return 0
    done
    return 1
}

env_pending_set() {
    local array_name="$1" key="$2" value="$3" pair updated=0 next=()
    local -n pending_ref="$array_name"
    for pair in "${pending_ref[@]}"; do
        if [ "${pair%%=*}" = "$key" ]; then
            next+=("$key=$value")
            updated=1
        else
            next+=("$pair")
        fi
    done
    [ "$updated" -eq 1 ] || next+=("$key=$value")
    pending_ref=("${next[@]}")
}
