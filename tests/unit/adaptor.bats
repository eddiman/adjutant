#!/usr/bin/env bats
# tests/unit/adaptor.bats — Tests for scripts/messaging/adaptor.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env_no_scripts
  source "${PROJECT_ROOT}/scripts/messaging/adaptor.sh"
}

teardown() { teardown_test_env; }

# --- Required functions: these must be overridden by a real backend ---
# The base stubs should fail loudly so missing overrides are caught early.

@test "adaptor: calling msg_send_text on the base stub fails with 'not implemented' because no backend has overridden it" {
  run msg_send_text "hello"
  assert_failure
  assert_output --partial "msg_send_text() not implemented"
}

@test "adaptor: calling msg_send_photo on the base stub fails with 'not implemented' because no backend has overridden it" {
  run msg_send_photo "/tmp/img.png" "caption"
  assert_failure
  assert_output --partial "msg_send_photo() not implemented"
}

@test "adaptor: calling msg_start_listener on the base stub fails with 'not implemented' because no backend has overridden it" {
  run msg_start_listener
  assert_failure
  assert_output --partial "msg_start_listener() not implemented"
}

@test "adaptor: calling msg_stop_listener on the base stub fails with 'not implemented' because no backend has overridden it" {
  run msg_stop_listener
  assert_failure
  assert_output --partial "msg_stop_listener() not implemented"
}

# --- Optional functions: these have safe defaults that silently succeed ---
# Backends only override these if they support the feature.

@test "adaptor: msg_react silently succeeds because emoji reactions are optional" {
  run msg_react "12345" "👍"
  assert_success
  assert_output ""
}

@test "adaptor: msg_typing silently succeeds because typing indicators are optional" {
  run msg_typing "start"
  assert_success
  assert_output ""
}

@test "adaptor: msg_authorize silently succeeds because sender validation is optional (allow-all default)" {
  run msg_authorize "user123"
  assert_success
  assert_output ""
}

# --- Default user identity ---

@test "adaptor: msg_get_user_id returns 'unknown' as the default when no backend identifies the user" {
  run msg_get_user_id
  assert_success
  assert_output "unknown"
}

# --- Interface completeness ---

@test "adaptor: all 8 interface functions are defined after sourcing adaptor.sh" {
  declare -f msg_send_text >/dev/null
  declare -f msg_send_photo >/dev/null
  declare -f msg_start_listener >/dev/null
  declare -f msg_stop_listener >/dev/null
  declare -f msg_react >/dev/null
  declare -f msg_typing >/dev/null
  declare -f msg_authorize >/dev/null
  declare -f msg_get_user_id >/dev/null
}
