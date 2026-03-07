#!/usr/bin/env bats

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks
  export ADJ_DIR="${TEST_ADJ_DIR}"

  mkdir -p "${TEST_ADJ_DIR}/knowledge_bases"
  cat > "${TEST_ADJ_DIR}/knowledge_bases/registry.yaml" <<'YAML'
knowledge_bases: []
YAML

  cp -R "${PROJECT_ROOT}/templates" "${TEST_ADJ_DIR}/templates"
  source "${COMMON}/paths.sh"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

@test "schedule integration: schedule_run_now supports kb_name and kb_operation" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"
  source "${TEST_ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
  source "${TEST_ADJ_DIR}/scripts/capabilities/schedule/install.sh"

  local kb_dir="${TEST_ADJ_DIR}/scheduled-kb"
  kb_create "scheduled" "${kb_dir}" "Scheduled KB" "inherit" "read-write"
  mkdir -p "${kb_dir}/scripts"
  cat > "${kb_dir}/scripts/fetch.sh" <<'EOF'
#!/bin/bash
echo "OK:scheduled fetch"
EOF
  chmod +x "${kb_dir}/scripts/fetch.sh"

  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
schedules:
  - name: "kb_fetch"
    description: "Run KB fetch"
    schedule: "0 9 * * 1-5"
    kb_name: "scheduled"
    kb_operation: "fetch"
    log: "state/kb_fetch.log"
    enabled: true
YAML

  run schedule_run_now "kb_fetch"
  assert_success
  assert_output "OK:scheduled fetch"
}
