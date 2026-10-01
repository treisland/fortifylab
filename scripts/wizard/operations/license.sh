# shellcheck shell=bash
# Module: operations/license
# Responsibility: License management menu and import/status actions.
# Requires: license helpers, UI helpers
# Exports: license_menu
# Side effects: May copy an operator-selected license into the ignored local input directory.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_LICENSE_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_LICENSE_LOADED=1

# License menu
# ============================================================

license_menu() {
    while true; do
        title "License files"
        local default_file="$FORTIFY_HOME_K8S/secrets/input/fortify.license"
        echo
        if ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
             fortify_resolve_license_file ) 2>/dev/null; then
            printf '  %s Configured Fortify license is readable\n' "$OK_MARK"
        else
            printf '  %s Configured Fortify license is unavailable\n' "$FAIL_MARK"
        fi
        echo
        echo "  1. Import to the backward-compatible repository-local location"
        echo "  2. Where to obtain a license"
        echo
        echo "  r. Return"
        echo
        ask choice "Select:"

        case "$choice" in
            1)
                ask src "Path to fortify.license file:"
                if [ ! -s "$src" ]; then
                    error "The selected file is missing, unreadable, or empty."
                else
                    mkdir -p "$(dirname "$default_file")"
                    cp "$src" "$default_file" && note "Imported license file."
                fi
                press_any ;;
            2)
                cat <<EOF

  Customers: download from your OpenText / Fortify customer portal.
  Trial:     request at https://www.opentext.com/products/fortify

  Set FORTIFY_LICENSE_FILE in .env to keep the file outside this repository,
  or use option 1 for the backward-compatible gitignored location.

EOF
                press_any ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
