#!/usr/bin/env bash
# Shared bash assertion helpers for Phase 3 smoke scripts.
# Sourced by smoke-local.sh and smoke-remote.sh.

# red/green ANSI for human-readable output (no-op in non-tty)
if [[ -t 1 ]]; then
  _ASS_RED=$'\033[0;31m'; _ASS_GREEN=$'\033[0;32m'; _ASS_RESET=$'\033[0m'
else
  _ASS_RED=""; _ASS_GREEN=""; _ASS_RESET=""
fi

assert_contains() {
  # $1 = haystack, $2 = needle (literal substring), $3 = label
  local haystack="$1" needle="$2" label="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    printf '%s[pass]%s %s\n' "$_ASS_GREEN" "$_ASS_RESET" "$label"
  else
    printf '%s[fail]%s %s\n' "$_ASS_RED" "$_ASS_RESET" "$label"
    printf '       expected substring: %q\n' "$needle"
    printf '       in: %s\n' "$haystack"
    return 1
  fi
}

assert_no_match() {
  # $1 = haystack, $2 = needle (literal substring), $3 = label
  local haystack="$1" needle="$2" label="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    printf '%s[pass]%s %s\n' "$_ASS_GREEN" "$_ASS_RESET" "$label"
  else
    printf '%s[fail]%s %s\n' "$_ASS_RED" "$_ASS_RESET" "$label"
    printf '       unexpected substring present: %q\n' "$needle"
    return 1
  fi
}

assert_exit_0() {
  # $1 = label, then the command (as remaining args)
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '%s[pass]%s %s\n' "$_ASS_GREEN" "$_ASS_RESET" "$label"
  else
    local rc=$?
    printf '%s[fail]%s %s (exit %d)\n' "$_ASS_RED" "$_ASS_RESET" "$label" "$rc"
    printf '       command: %s\n' "$*"
    return 1
  fi
}

assert_eq() {
  # $1 = actual, $2 = expected, $3 = label
  local actual="$1" expected="$2" label="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf '%s[pass]%s %s\n' "$_ASS_GREEN" "$_ASS_RESET" "$label"
  else
    printf '%s[fail]%s %s\n' "$_ASS_RED" "$_ASS_RESET" "$label"
    printf '       actual:   %q\n' "$actual"
    printf '       expected: %q\n' "$expected"
    return 1
  fi
}
