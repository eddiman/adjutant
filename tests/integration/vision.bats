#!/usr/bin/env bats
# tests/integration/vision.bats — Integration tests for scripts/capabilities/vision/vision.sh
#
# vision.sh is a standalone script that:
#   - Takes an image path and optional prompt
#   - Runs opencode with --format json and -f <image>
#   - Parses NDJSON output for text parts
#   - Detects model-not-found errors
#   - Returns the assembled vision analysis on stdout

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

VISION_SCRIPT="${PROJECT_ROOT}/scripts/capabilities/vision/vision.sh"

setup() {
  setup_test_env
  setup_mocks
  create_mock_opencode_reply "I see a cat sitting on a desk" "vision-session-001"

  # Create a test image file
  TEST_IMAGE="${TEST_ADJ_DIR}/photos/test_image.jpg"
  echo "fake JPEG image data" > "${TEST_IMAGE}"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- Happy path ---

@test "vision: returns the text analysis from opencode NDJSON output" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_output --partial "I see a cat sitting on a desk"
}

@test "vision: calls opencode with the --format json flag" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_args_contain "opencode" "--format json"
}

@test "vision: calls opencode with -f flag to attach the image" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_args_contain "opencode" "-f"
  assert_mock_args_contain "opencode" "${TEST_IMAGE}"
}

@test "vision: uses the default description prompt when no prompt is provided" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_args_contain "opencode" "Describe what you see"
}

@test "vision: uses a custom prompt when provided as second argument" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}" "What breed is this cat?"
  assert_success
  assert_mock_args_contain "opencode" "What breed is this cat?"
}

# --- Model selection ---

@test "vision: uses the default model (anthropic/claude-haiku-4-5) when no model file exists" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_args_contain "opencode" "anthropic/claude-haiku-4-5"
}

@test "vision: uses the model from state/telegram_model.txt when it exists" {
  seed_model_file "anthropic/claude-sonnet-4-20250514"
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_args_contain "opencode" "anthropic/claude-sonnet-4-20250514"
}

# --- Input validation ---

@test "vision: exits with error when no image path is provided" {
  run bash "${VISION_SCRIPT}"
  assert_failure
  assert_output --partial "No image path provided"
}

@test "vision: exits with error when the image file does not exist" {
  run bash "${VISION_SCRIPT}" "/nonexistent/image.jpg"
  assert_failure
  assert_output --partial "Image file not found"
}

# --- Error handling ---

@test "vision: reports model-not-found error gracefully" {
  create_mock_opencode '{"type":"error","error":{"name":"ModelNotFoundError","data":{"message":"Model not found"}}}'
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_output --partial "doesn't support vision"
}

@test "vision: returns an error message when opencode returns no text output" {
  create_mock_opencode '{"type":"session.create","sessionID":"empty-session"}'
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_failure
  assert_output --partial "couldn't analyse"
}

# --- Single invocation ---

@test "vision: calls opencode exactly once per invocation" {
  run bash "${VISION_SCRIPT}" "${TEST_IMAGE}"
  assert_success
  assert_mock_call_count "opencode" 1
}
