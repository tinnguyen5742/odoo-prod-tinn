#!/usr/bin/env bash
# Shared by the image build and .github/workflows/docker-publish.yml.
#
#   discover-addons.sh modules ROOT
#   discover-addons.sh duplicates ROOT
#   discover-addons.sh addons-path ROOT
#   discover-addons.sh flatten ROOT
#   discover-addons.sh requirements ROOT
#   discover-addons.sh stage-requirements ROOT DEST
#   discover-addons.sh install-requirements ROOT
#   discover-addons.sh apply-config ROOT CONF
#
# A module is a directory that contains __manifest__.py.
# addons-path prints ROOT, then every other direct parent of a module,
# byte-sorted. flatten moves every module to ROOT/<name> and removes leftover
# wrapper dirs. requirements lists only ROOT/*/requirements.txt.
# stage-requirements copies those files to DEST/<child>/requirements.txt
# before flatten deletes the wrapper directory. DEST must sit outside ROOT.
set -euo pipefail

usage() {
  echo "usage: discover-addons.sh modules|duplicates|addons-path|flatten|requirements|install-requirements ROOT" >&2
  echo "       discover-addons.sh stage-requirements ROOT DEST" >&2
  echo "       discover-addons.sh apply-config ROOT CONF" >&2
  exit 2
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  usage
fi

cmd=$1
if [ ! -d "$2" ]; then
  echo "discover-addons: not a directory: $2" >&2
  exit 1
fi
ROOT=$(cd "$2" && pwd)
CONF=${3:-}

case "$cmd" in
  apply-config | stage-requirements)
    [ "$#" -eq 3 ] || usage
    ;;
  modules | duplicates | addons-path | flatten | requirements | install-requirements)
    [ "$#" -eq 2 ] || usage
    ;;
  *)
    usage
    ;;
esac

mapfile -t MODULE_DIRS < <(find "$ROOT" -type f -name '__manifest__.py' -not -path '*/.git/*' -printf '%h\n')

cmd_modules() {
  local dir
  if [ "${#MODULE_DIRS[@]}" -eq 0 ]; then
    return 0
  fi
  for dir in "${MODULE_DIRS[@]}"; do
    basename "$dir"
  done | LC_ALL=C sort
}

cmd_duplicates() {
  cmd_modules | uniq -d
}

cmd_addons_path() {
  local dir parent extra joined
  local -a extras=()
  for dir in "${MODULE_DIRS[@]}"; do
    if [ "$dir" = "$ROOT" ]; then
      echo "discover-addons: ${ROOT}/__manifest__.py cannot sit in the addons root" >&2
      exit 1
    fi
    parent=$(dirname "$dir")
    if [ "$parent" != "$ROOT" ]; then
      extras+=("$parent")
    fi
  done
  if [ "${#extras[@]}" -eq 0 ]; then
    printf '%s\n' "$ROOT"
    return 0
  fi
  joined=$ROOT
  while IFS= read -r extra; do
    [ -z "$extra" ] && continue
    joined="${joined},${extra}"
  done < <(printf '%s\n' "${extras[@]}" | LC_ALL=C sort -u)
  printf '%s\n' "$joined"
}

cmd_flatten() {
  local dir name dest child
  local -a ordered=()
  if [ "${#MODULE_DIRS[@]}" -eq 0 ]; then
    return 0
  fi
  mapfile -t ordered < <(
    for dir in "${MODULE_DIRS[@]}"; do
      printf '%d\t%s\n' "${#dir}" "$dir"
    done | LC_ALL=C sort -nr -k1,1 | cut -f2-
  )
  for dir in "${ordered[@]}"; do
    name=$(basename "$dir")
    dest="${ROOT}/${name}"
    if [ "$dir" = "$dest" ]; then
      continue
    fi
    if [ -e "$dest" ]; then
      echo "discover-addons: cannot flatten ${dir}: ${dest} already exists" >&2
      exit 1
    fi
    echo "flatten: ${dir} -> ${dest}"
    mv "$dir" "$dest"
  done
  while IFS= read -r -d '' child; do
    if [ -f "${child}/__manifest__.py" ]; then
      continue
    fi
    if [ -n "$(find "$child" -type f -name '__manifest__.py' -print -quit)" ]; then
      continue
    fi
    echo "flatten: prune ${child}"
    rm -rf "$child"
  done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -print0)
}

cmd_requirements() {
  find "$ROOT" -mindepth 2 -maxdepth 2 -type f -name 'requirements.txt' -not -path '*/.git/*' | LC_ALL=C sort
}

cmd_stage_requirements() {
  local dest=$1 req name req_list parent
  parent=$(dirname "$dest")
  mkdir -p "$parent"
  parent=$(cd "$parent" && pwd)
  dest="${parent}/$(basename "$dest")"
  case "$dest" in
    "$ROOT" | "$ROOT"/*)
      echo "discover-addons: stage-requirements dest must be outside ${ROOT}" >&2
      exit 1
      ;;
  esac
  mkdir -p "$dest"
  req_list=$(cmd_requirements)
  if [ -z "$req_list" ]; then
    echo "No requirements.txt in direct children of ${ROOT}"
    return 0
  fi
  while IFS= read -r req; do
    [ -z "$req" ] && continue
    name=$(basename "$(dirname "$req")")
    mkdir -p "${dest}/${name}"
    cp "$req" "${dest}/${name}/requirements.txt"
    echo "stage-requirements: ${req} -> ${dest}/${name}/requirements.txt"
  done <<< "$req_list"
}

cmd_install_requirements() {
  local req_list req
  req_list=$(cmd_requirements)
  if [ -z "$req_list" ]; then
    echo "No requirements.txt in direct children of ${ROOT}"
    return 0
  fi
  while IFS= read -r req; do
    [ -z "$req" ] && continue
    echo "Installing requirements from ${req}"
    pip3 install --break-system-packages -r "$req"
  done <<< "$req_list"
}

# Drop entries equal to ROOT or under ROOT, then append what remains
# after the discovered parents. A second run sees the same line.
merge_addons_path() {
  local raw entry suffix old_ifs
  local -a entries=() kept=()
  raw=${1#*=}
  raw=${raw#"${raw%%[![:space:]]*}"}
  raw=${raw%"${raw##*[![:space:]]}"}
  old_ifs=$IFS
  IFS=,
  read -r -a entries <<< "$raw"
  IFS=$old_ifs
  for entry in "${entries[@]}"; do
    entry=${entry#"${entry%%[![:space:]]*}"}
    entry=${entry%"${entry##*[![:space:]]}"}
    [ -z "$entry" ] && continue
    case "$entry" in
      "$ROOT" | "$ROOT"/*) ;;
      *) kept+=("$entry") ;;
    esac
  done
  if [ "${#kept[@]}" -eq 0 ]; then
    printf '%s' "$2"
  else
    suffix=$(IFS=,; printf '%s' "${kept[*]}")
    printf '%s,%s' "$2" "$suffix"
  fi
}

cmd_apply_config() {
  local conf=$1 discovered merged line tmp found
  [ -f "$conf" ] || {
    echo "discover-addons: no config file: ${conf}" >&2
    exit 1
  }
  discovered=$(cmd_addons_path) || exit 1
  tmp=$(mktemp)
  found=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      'addons_path '* | 'addons_path='*)
        found=$((found + 1))
        merged=$(merge_addons_path "$line" "$discovered")
        printf 'addons_path = %s\n' "$merged"
        ;;
      *)
        printf '%s\n' "$line"
        ;;
    esac
  done < "$conf" > "$tmp"
  if [ "$found" -ne 1 ]; then
    rm -f "$tmp"
    echo "discover-addons: expected one addons_path line in ${conf}" >&2
    exit 1
  fi
  cat "$tmp" > "$conf"
  rm -f "$tmp"
  printf 'addons_path = %s\n' "$merged"
}

case "$cmd" in
  modules) cmd_modules ;;
  duplicates) cmd_duplicates ;;
  addons-path) cmd_addons_path ;;
  flatten) cmd_flatten ;;
  requirements) cmd_requirements ;;
  stage-requirements) cmd_stage_requirements "$CONF" ;;
  install-requirements) cmd_install_requirements ;;
  apply-config) cmd_apply_config "$CONF" ;;
esac
