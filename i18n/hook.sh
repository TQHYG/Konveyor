# Konveyor Chinese localization hook (fork only).
#
# Sourced by install.sh. It applies the translations in i18n/zh_CN.json to the
# working tree just before a build and restores the originals when install.sh
# exits, so the checkout stays a clean mirror of upstream and `git merge
# upstream/main` never conflicts.
#
# All of the real work lives in tools/i18n/i18n.py. This file only decides
# *when* to apply and revert. Delete the source line from install.sh (or this
# file) to disable the localization.

KONVEYOR_I18N_LANG="${KONVEYOR_I18N_LANG:-zh_CN}"
KONVEYOR_I18N_ACTIVE=false

konveyor_i18n_tool() {
    printf '%s' "${SOURCE_DIR:-$INSTALL_DIR}/tools/i18n/i18n.py"
}

konveyor_i18n_available() {
    [[ -f $(konveyor_i18n_tool) && -f "${SOURCE_DIR:-$INSTALL_DIR}/i18n/${KONVEYOR_I18N_LANG}.json" ]] || return 1
    command -v python3 >/dev/null 2>&1 || return 1
}

konveyor_i18n_apply() {
    command -v python3 >/dev/null 2>&1 || return 0
    if [[ ! -f "${SOURCE_DIR:-$INSTALL_DIR}/i18n/${KONVEYOR_I18N_LANG}.json" ]]; then
        return 0
    fi
    if $KONVEYOR_I18N_ACTIVE; then
        return 0
    fi
    local repo="${SOURCE_DIR:-$INSTALL_DIR}"
    if ! python3 "$(konveyor_i18n_tool)" --repo "$repo" apply --lang "$KONVEYOR_I18N_LANG"; then
        say "Note: could not apply the ${KONVEYOR_I18N_LANG} translation; building untranslated"
        return 0
    fi
    KONVEYOR_I18N_ACTIVE=true
    # shellcheck disable=SC2064
    trap konveyor_i18n_revert EXIT
}

konveyor_i18n_revert() {
    $KONVEYOR_I18N_ACTIVE || return 0
    local repo="${SOURCE_DIR:-$INSTALL_DIR}"
    KONVEYOR_I18N_ACTIVE=false
    python3 "$(konveyor_i18n_tool)" --repo "$repo" revert >/dev/null 2>&1 || true
}
