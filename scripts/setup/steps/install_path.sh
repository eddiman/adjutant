#!/bin/bash
# scripts/setup/steps/install_path.sh — Step 2: Installation Path
#
# Confirms or selects the installation directory.
# For fresh installs: asks user to confirm or choose a path.
# For existing installs: shows current path and moves on.
#
# Sets:
#   WIZARD_INSTALL_PATH — the confirmed installation path
#   ADJ_DIR — updated to match WIZARD_INSTALL_PATH

# Requires: helpers.sh sourced

step_install_path() {
  wiz_step 2 7 "Installation Path"
  echo ""

  local default_path
  if [ -n "${ADJ_DIR:-}" ] && [ -d "${ADJ_DIR}" ] && [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
    # Existing install detected
    default_path="${ADJ_DIR}"
    wiz_ok "Existing installation found at: ${default_path}"
    WIZARD_INSTALL_PATH="${default_path}"
    return 0
  fi

  # Fresh install — default to current working directory
  default_path="$(pwd)"
  local chosen_path
  chosen_path=$(wiz_input "Installation path" "$default_path")
  chosen_path=$(expand_path "$chosen_path")

  # Validate the chosen path
  if [ -f "${chosen_path}/adjutant.yaml" ]; then
    wiz_ok "Found existing installation at: ${chosen_path}"
    WIZARD_INSTALL_PATH="${chosen_path}"
    ADJ_DIR="${chosen_path}"
    export ADJ_DIR
    return 0
  fi

  # Create the directory if it doesn't exist
  if [ ! -d "${chosen_path}" ]; then
    if wiz_confirm "Directory doesn't exist. Create ${chosen_path}?" "Y"; then
      if [ "${DRY_RUN:-}" = "true" ]; then
        dry_run_would "mkdir -p ${chosen_path}"
        wiz_ok "Would create ${chosen_path}"
      else
        mkdir -p "${chosen_path}" || {
          wiz_fail "Could not create ${chosen_path}"
          return 1
        }
        wiz_ok "Created ${chosen_path}"
      fi
    else
      wiz_fail "Installation cancelled — no directory created"
      return 1
    fi
  fi

  WIZARD_INSTALL_PATH="${chosen_path}"
  ADJ_DIR="${chosen_path}"
  export ADJ_DIR

  # Create the base directory structure
  local dirs=(state journal identity prompts photos screenshots scripts docs)
  for d in "${dirs[@]}"; do
    if [ "${DRY_RUN:-}" = "true" ]; then
      dry_run_would "mkdir -p ${WIZARD_INSTALL_PATH}/${d}"
    else
      mkdir -p "${WIZARD_INSTALL_PATH}/${d}"
    fi
  done
  if [ "${DRY_RUN:-}" = "true" ]; then
    wiz_ok "Would create directory structure"
  else
    wiz_ok "Created directory structure"
  fi

  return 0
}
