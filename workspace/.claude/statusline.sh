#!/usr/bin/env bash
# MARE container status line — no jq dependency

input=$(cat)

get_json() {
  printf '%s' "$input" \
    | grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" \
    | head -1 | sed 's/.*":[[:space:]]*"\(.*\)"/\1/'
}
get_nested() {
  printf '%s' "$input" \
    | grep -o "\"$1\"[[:space:]]*:[[:space:]]*{[^}]*}" \
    | grep -o "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" \
    | head -1 | sed 's/.*":[[:space:]]*"\(.*\)"/\1/'
}

version=$(get_json "version")
model=$(get_nested "model" "display_name")
[ -z "$model" ] && model=$(get_json "display_name")
cwd=$(get_json "cwd")
[ -z "$cwd" ] && cwd=$(get_nested "workspace" "current_dir")

ctx_size=$(printf '%s' "$input" \
  | grep -o '"context_window_size"[[:space:]]*:[[:space:]]*[0-9]*' \
  | head -1 | sed 's/.*:[[:space:]]*//')

transcript_path=$(printf '%s' "$input" \
  | grep -o '"transcript_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*":[[:space:]]*"\(.*\)"/\1/')

input_tokens=0
if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
  last=$(grep '"type"[[:space:]]*:[[:space:]]*"assistant"' "$transcript_path" \
    | grep '"input_tokens"' | tail -1)
  if [ -n "$last" ]; then
    _i=$(printf '%s' "$last" | grep -o '"input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')
    _r=$(printf '%s' "$last" | grep -o '"cache_read_input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')
    _c=$(printf '%s' "$last" | grep -o '"cache_creation_input_tokens"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')
    input_tokens=$(( ${_i:-0} + ${_r:-0} + ${_c:-0} ))
  fi
fi

used_pct=""
[ "$input_tokens" -gt 0 ] && [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ] 2>/dev/null \
  && used_pct=$(( input_tokens * 100 / ctx_size ))

# Active sample: newest dir under workspace/status/
sample=""
if [ -d /workspace/status ]; then
  sample=$(ls -1t /workspace/status 2>/dev/null | head -1)
fi

# Which disassembler MCP is wired in
backend=""
if [ -f /workspace/.mcp.json ]; then
  if   grep -q '"binaryninja"' /workspace/.mcp.json 2>/dev/null; then backend="binja"
  elif grep -q '"ghidra"'      /workspace/.mcp.json 2>/dev/null; then backend="ghidra"
  elif grep -q '"ida"'         /workspace/.mcp.json 2>/dev/null; then backend="ida"
  fi
fi

# Short path: replace /workspace with 🔬
short_path="${cwd:-$PWD}"
short_path="${short_path/#\/workspace/🔬}"
short_path="${short_path/#\/home\/agent/🐳}"

reset='\033[0m'
red='\033[38;5;210m'
orange='\033[38;5;223m'
yellow='\033[38;5;228m'
green='\033[38;5;157m'
cyan='\033[38;5;159m'
magenta='\033[38;5;219m'
warn='\033[38;5;216m'

fmt_k() {
  local n="$1"
  if   [ "$n" -ge 10000 ]; then printf '%d.%01dw' $((n/10000)) $(((n%10000)/1000))
  elif [ "$n" -ge 1000 ];  then printf '%d.%01dk' $((n/1000))  $(((n%1000)/100))
  else printf '%d' "$n"
  fi
}

line=""
line+="$(printf "${red}%s${reset}" "$short_path") "
[ -n "$version" ] && line+="$(printf "${orange}v%s${reset}" "$version") "

if [ -n "$model" ]; then
  case "$model" in
    *Opus*4.7*1M*) model="Op4.7-1M" ;;
    *Opus*4.7*)    model="Op4.7" ;;
    *Opus*4.6*1M*) model="Op4.6-1M" ;;
    *Opus*4.6*)    model="Op4.6" ;;
    *Sonnet*4.6*)  model="So4.6" ;;
    *Haiku*)       model="Haiku" ;;
  esac
  line+="$(printf "${yellow}%s${reset}" "$model") "
fi

if [ "$input_tokens" -gt 0 ] && [ -n "$ctx_size" ]; then
  [ "${used_pct:-0}" -ge 70 ] 2>/dev/null && col="$warn" || col="$green"
  line+="$(printf "${col}%s/%s${reset}" "$(fmt_k $input_tokens)" "$(fmt_k $ctx_size)") "
fi

[ -n "$backend" ] && line+="$(printf "${cyan}%s${reset}" "$backend") "
[ -n "$sample" ]  && line+="$(printf "${magenta}☣ %s${reset}" "$sample") "

printf '%b\n' "$line"
