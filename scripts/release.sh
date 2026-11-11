#!/usr/bin/env bash
# Bump submodule pointers to the latest release tag on the branch in
# .gitmodules, then cut the next annotated vX.Y.Z tag. Pushing that tag
# triggers .github/workflows/docker-publish.yml.
#
#   scripts/release.sh
#   scripts/release.sh --dry-run
#   scripts/release.sh --bump minor --push
#   scripts/release.sh --submodule HRM --tag v0.1.0
#
# Release steps: docs/dev-workflow.md
set -euo pipefail

export GIT_TERMINAL_PROMPT=0

usage() {
  cat <<'EOF'
usage: release.sh [options]

Update submodules in .gitmodules to the latest release tag on each tracked
branch, commit the new gitlink SHAs, and create the next annotated vX.Y.Z tag.

Prefers <branch>/vX.Y.Z (e.g. client/tanphong/v0.0.2), else vX.Y.Z reachable
from origin/<branch>. Only tagged commits are released.

  --bump patch|minor|major  Semver bump from the latest vX.Y.Z tag (default: patch)
  --tag vX.Y.Z              Use this tag instead of bumping
  --message TEXT            Extra line for the commit and tag message
  --submodule PATH          Only update this submodule (repeatable; name or path)
  --branch NAME             Parent branch that must be checked out (default: main)
  --no-tag                  Bump submodules only; do not create a tag
  --always-tag              Create a tag even if no submodule pointer changed
  --push                    Push the commit and tag to origin (triggers GHCR)
  --dry-run                 Fetch and report; do not checkout, commit, tag, or push
  -h, --help
EOF
}

log() { printf '%s\n' "$*"; }
err() { printf 'release.sh: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

bump=patch
explicit_tag=
message=
require_branch=main
push=0
dry_run=0
do_tag=1
always_tag=0
declare -a only_submodules=()

while [[ $# -gt 0 ]]; do
  case $1 in
    --bump)
      [[ $# -ge 2 ]] || die "option $1 needs a value"
      bump=$2
      shift 2
      ;;
    --tag)
      [[ $# -ge 2 ]] || die "option $1 needs a value"
      explicit_tag=$2
      shift 2
      ;;
    --message)
      [[ $# -ge 2 ]] || die "option $1 needs a value"
      message=$2
      shift 2
      ;;
    --submodule)
      [[ $# -ge 2 ]] || die "option $1 needs a value"
      only_submodules+=("$2")
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "option $1 needs a value"
      require_branch=$2
      shift 2
      ;;
    --no-tag)
      do_tag=0
      shift
      ;;
    --always-tag)
      always_tag=1
      shift
      ;;
    --push)
      push=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case $bump in
  patch | minor | major) ;;
  *) die "--bump must be patch, minor, or major (got ${bump})" ;;
esac

if [[ $do_tag -eq 0 && $always_tag -eq 1 ]]; then
  die "--no-tag and --always-tag cannot be used together"
fi

if [[ $do_tag -eq 0 && -n $explicit_tag ]]; then
  die "--no-tag and --tag cannot be used together"
fi

if [[ $push -eq 1 && $dry_run -eq 1 ]]; then
  die "--push and --dry-run cannot be used together"
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repository"
cd "$ROOT"

[[ -f .gitmodules ]] || die "no .gitmodules in ${ROOT}"

want_submodule() {
  local path=$1 name=$2 base
  base=$(basename "$path")
  if [[ ${#only_submodules[@]} -eq 0 ]]; then
    return 0
  fi
  local s
  for s in "${only_submodules[@]}"; do
    if [[ $s == "$path" || $s == "$name" || $s == "$base" ]]; then
      return 0
    fi
  done
  return 1
}

# Lines: name<TAB>path<TAB>branch
declare -a SUBS=()
declare -A SUB_SEEN=()
declare -A ALL_SM_PATHS=()

while read -r key path; do
  [[ -n ${key:-} && -n ${path:-} ]] || continue
  name=${key#submodule.}
  name=${name%.path}
  ALL_SM_PATHS["$path"]=1
  want_submodule "$path" "$name" || continue
  branch=$(git config --file .gitmodules --get "submodule.${name}.branch" || true)
  [[ -n $branch ]] || die "submodule ${name} has no branch in .gitmodules"
  SUBS+=("${name}"$'\t'"${path}"$'\t'"${branch}")
  SUB_SEEN["$path"]=1
  SUB_SEEN["$name"]=1
  SUB_SEEN["$(basename "$path")"]=1
done < <(git config --file .gitmodules --get-regexp '^submodule\..*\.path$')

if [[ ${#SUBS[@]} -eq 0 ]]; then
  die "no matching submodule in .gitmodules"
fi

if [[ ${#only_submodules[@]} -gt 0 ]]; then
  for s in "${only_submodules[@]}"; do
    [[ -n ${SUB_SEEN[$s]+x} ]] || die "unknown submodule: ${s}"
  done
fi

is_submodule_path() {
  [[ -n ${ALL_SM_PATHS[$1]+x} ]]
}

porcelain_path() {
  local line=$1
  local rest=${line:3}
  if [[ $rest == *' -> '* ]]; then
    rest=${rest##* -> }
  fi
  printf '%s' "$rest"
}

assert_parent_clean() {
  local line path xy
  local -a untracked=()
  local -a dirty=()
  while IFS= read -r line; do
    [[ -n $line ]] || continue
    xy=${line:0:2}
    path=$(porcelain_path "$line")
    if is_submodule_path "$path"; then
      continue
    fi
    if [[ $xy == '??' ]]; then
      untracked+=("$path")
      continue
    fi
    dirty+=("$line")
  done < <(git status --porcelain)
  if [[ ${#dirty[@]} -gt 0 ]]; then
    if [[ $dry_run -eq 1 ]]; then
      err "warning: working tree has changes outside submodule gitlinks (would abort a real run):"
      local d
      for d in "${dirty[@]}"; do
        err "  ${d}"
      done
    else
      die "working tree has changes outside submodule gitlinks: ${dirty[0]}"
    fi
  fi
  if [[ ${#untracked[@]} -gt 0 ]]; then
    err "warning: untracked files (not committed):"
    local u
    for u in "${untracked[@]}"; do
      err "  ${u}"
    done
  fi
}

assert_submodule_clean() {
  local path=$1
  local dirty
  dirty=$(git -C "$path" status --porcelain)
  if [[ -n $dirty ]]; then
    err "submodule ${path} has uncommitted changes:"
    printf '%s\n' "$dirty" >&2
    exit 1
  fi
}

short() {
  printf '%s' "${1:0:7}"
}

normalize_tag() {
  local raw=$1
  raw=${raw#v}
  [[ $raw =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "tag must be vX.Y.Z (got ${1})"
  printf 'v%s' "$raw"
}

latest_semver_tag() {
  local tag
  while IFS= read -r tag; do
    [[ -n $tag ]] || continue
    if [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      printf '%s' "$tag"
      return 0
    fi
  done < <(git tag -l 'v*.*.*' --sort=-v:refname)
  return 1
}

# Latest release tag in a submodule. Prefer <branch>/vX.Y.Z, else vX.Y.Z
# reachable from origin/<branch>. Ignores non-semver tags (e.g. KPP).
latest_submodule_tag() {
  local path=$1 branch=$2
  local tag
  while IFS= read -r tag; do
    [[ -n $tag ]] || continue
    if [[ $tag =~ ^(.+)/v[0-9]+\.[0-9]+\.[0-9]+$ && ${BASH_REMATCH[1]} == "$branch" ]]; then
      printf '%s' "$tag"
      return 0
    fi
  done < <(git -C "$path" tag -l "${branch}/v*.*.*" --sort=-v:refname)

  while IFS= read -r tag; do
    [[ -n $tag ]] || continue
    if [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      printf '%s' "$tag"
      return 0
    fi
  done < <(git -C "$path" tag -l 'v*.*.*' --merged "origin/${branch}" --sort=-v:refname)

  return 1
}

bump_tag() {
  local latest=$1 kind=$2
  local major minor patch
  if [[ -z $latest ]]; then
    printf 'v0.0.1'
    return 0
  fi
  [[ $latest =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || die "cannot parse tag ${latest}"
  major=${BASH_REMATCH[1]}
  minor=${BASH_REMATCH[2]}
  patch=${BASH_REMATCH[3]}
  case $kind in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch)
      patch=$((patch + 1))
      ;;
  esac
  printf 'v%d.%d.%d' "$major" "$minor" "$patch"
}

current_branch=$(git rev-parse --abbrev-ref HEAD)
[[ $current_branch == "$require_branch" ]] || die "must be on ${require_branch} (now ${current_branch})"

assert_parent_clean

log "==> fetch origin (parent)"
git fetch origin
git fetch origin --tags

if git rev-parse --verify -q "origin/${require_branch}" >/dev/null; then
  local_head=$(git rev-parse HEAD)
  remote_head=$(git rev-parse "origin/${require_branch}")
  if [[ $local_head != "$remote_head" ]]; then
    if git merge-base --is-ancestor HEAD "origin/${require_branch}"; then
      if [[ $dry_run -eq 1 ]]; then
        log "would fast-forward ${require_branch} to origin/${require_branch} ($(short "$remote_head"))"
      else
        log "==> fast-forward ${require_branch} to origin/${require_branch}"
        git merge --ff-only "origin/${require_branch}"
      fi
    elif git merge-base --is-ancestor "origin/${require_branch}" HEAD; then
      log "local ${require_branch} is ahead of origin/${require_branch}"
    else
      die "${require_branch} has diverged from origin/${require_branch}"
    fi
  fi
fi

latest_tag=
if latest_tag=$(latest_semver_tag); then
  log "latest tag: ${latest_tag}"
else
  latest_tag=
  log "latest tag: (none)"
fi

if [[ -n $explicit_tag ]]; then
  new_tag=$(normalize_tag "$explicit_tag")
else
  new_tag=$(bump_tag "$latest_tag" "$bump")
fi

if [[ $do_tag -eq 1 ]]; then
  if git rev-parse --verify -q "refs/tags/${new_tag}" >/dev/null; then
    die "tag ${new_tag} already exists locally"
  fi
  if git ls-remote --exit-code --tags origin "refs/tags/${new_tag}" >/dev/null 2>&1; then
    die "tag ${new_tag} already exists on origin"
  fi
fi

declare -a CHANGED_PATHS=()
declare -a CHANGE_LINES=()
declare -a SUMMARY_ROWS=()

update_one() {
  local name=$1 path=$2 branch=$3
  local pinned current remote tag tag_sha new_sha dirty status

  if [[ ! -e ${path}/.git ]]; then
    log "==> init ${path}"
    git submodule update --init --recursive -- "$path"
  fi
  [[ -d $path ]] || die "submodule path missing: ${path}"
  [[ -e ${path}/.git ]] || die "not a submodule checkout: ${path}"

  pinned=$(git ls-tree HEAD "$path" | awk '{print $3}')
  [[ -n $pinned ]] || die "no gitlink at HEAD for ${path}"

  if [[ $dry_run -eq 1 ]]; then
    dirty=$(git -C "$path" status --porcelain)
    if [[ -n $dirty ]]; then
      err "warning: submodule ${path} has uncommitted changes (would abort a real run)"
    fi
  else
    assert_submodule_clean "$path"
  fi

  log "==> ${path}  branch ${branch}"
  git -C "$path" fetch --prune origin "$branch"
  git -C "$path" fetch --tags origin
  git -C "$path" rev-parse --verify -q "origin/${branch}" >/dev/null \
    || die "${path}: origin/${branch} does not exist"

  current=$(git -C "$path" rev-parse HEAD)
  remote=$(git -C "$path" rev-parse "origin/${branch}")

  tag=$(latest_submodule_tag "$path" "$branch") \
    || die "${path}: no release tag for ${branch} (need ${branch}/vX.Y.Z, or vX.Y.Z on origin/${branch})"
  tag_sha=$(git -C "$path" rev-parse "${tag}^{commit}")

  if [[ $tag_sha != "$remote" ]]; then
    if git -C "$path" merge-base --is-ancestor "$tag_sha" "$remote"; then
      :
    elif git -C "$path" merge-base --is-ancestor "$remote" "$tag_sha"; then
      :
    else
      die "${path}: tag ${tag} ($(short "$tag_sha")) has diverged from origin/${branch}"
    fi
  fi

  if [[ $dry_run -eq 1 ]]; then
    new_sha=$tag_sha
  else
    git -C "$path" checkout --quiet --detach "$tag"
    new_sha=$(git -C "$path" rev-parse HEAD)
    [[ $new_sha == "$tag_sha" ]] || die "${path}: HEAD is not ${tag} after checkout"
    assert_submodule_clean "$path"
  fi

  if [[ $pinned == "$new_sha" ]]; then
    status="unchanged"
  else
    status="bump"
    CHANGED_PATHS+=("$path")
    CHANGE_LINES+=("${path}: $(short "$pinned") -> $(short "$new_sha") (${tag})")
  fi
  SUMMARY_ROWS+=("${path}"$'\t'"$(short "$pinned")"$'\t'"$(short "$current")"$'\t'"$(short "$new_sha")"$'\t'"${tag}"$'\t'"${status}")
  log "    pinned $(short "$pinned")  local $(short "$current")  ${tag} $(short "$new_sha")  ${status}"
}

for entry in "${SUBS[@]}"; do
  IFS=$'\t' read -r name path branch <<<"$entry"
  update_one "$name" "$path" "$branch"
done

log
log "submodule summary:"
printf '    %-42s %-8s %-8s %-8s %-28s %s\n' PATH PINNED LOCAL NEW TAG STATUS
for row in "${SUMMARY_ROWS[@]}"; do
  IFS=$'\t' read -r path pinned current new_sha tag status <<<"$row"
  printf '    %-42s %-8s %-8s %-8s %-28s %s\n' "$path" "$pinned" "$current" "$new_sha" "$tag" "$status"
done
log

committed=0
tagged=0

names_csv() {
  local path names=()
  for path in "${CHANGED_PATHS[@]}"; do
    names+=("$(basename "$path")")
  done
  (IFS=', '; printf '%s' "${names[*]}")
}

body_text() {
  local line
  if [[ ${#CHANGE_LINES[@]} -gt 0 ]]; then
    printf 'Bumped:\n'
    for line in "${CHANGE_LINES[@]}"; do
      printf -- '- %s\n' "$line"
    done
  fi
  if [[ -n $message ]]; then
    if [[ ${#CHANGE_LINES[@]} -gt 0 ]]; then
      printf '\n'
    fi
    printf '%s\n' "$message"
  fi
}

if [[ ${#CHANGED_PATHS[@]} -gt 0 ]]; then
  if [[ $dry_run -eq 1 ]]; then
    log "would commit: chore: bump $(names_csv)"
    body_text | sed 's/^/    /'
  else
    git add -- "${CHANGED_PATHS[@]}"
    commit_msg="chore: bump $(names_csv)"
    git commit -m "$commit_msg" -m "$(body_text)"
    committed=1
    log "committed $(git rev-parse --short HEAD): ${commit_msg}"
  fi
else
  log "no submodule pointer changed"
fi

head_sha=$(git rev-parse HEAD)
latest_tag_sha=
if [[ -n $latest_tag ]]; then
  latest_tag_sha=$(git rev-list -n 1 "$latest_tag")
fi

should_tag=0
if [[ $do_tag -eq 1 ]]; then
  if [[ $always_tag -eq 1 || -n $explicit_tag ]]; then
    should_tag=1
  elif [[ $committed -eq 1 || $dry_run -eq 1 && ${#CHANGED_PATHS[@]} -gt 0 ]]; then
    should_tag=1
  elif [[ -n $latest_tag_sha && $head_sha != "$latest_tag_sha" ]]; then
    should_tag=1
  fi
fi

if [[ $do_tag -eq 1 && $should_tag -eq 0 ]]; then
  if [[ -n $latest_tag ]]; then
    log "HEAD is already ${latest_tag}; skip tag (pass --always-tag to tag anyway)"
  else
    log "nothing to tag (pass --always-tag to create ${new_tag})"
  fi
fi

if [[ $should_tag -eq 1 ]]; then
  tag_msg="release: ${new_tag}"
  if [[ $dry_run -eq 1 ]]; then
    log "would tag ${new_tag}  ${tag_msg}"
    body_text | sed 's/^/    /'
  else
    if [[ -n $(body_text) ]]; then
      git tag -a "$new_tag" -m "$tag_msg" -m "$(body_text)"
    else
      git tag -a "$new_tag" -m "$tag_msg"
    fi
    tagged=1
    log "tagged ${new_tag}"
  fi
fi

if [[ $dry_run -eq 1 ]]; then
  log
  log "dry-run only; nothing was committed or tagged"
  exit 0
fi

push_tag() {
  local tag=$1
  log "==> push origin ${tag}  (triggers GHCR build)"
  git push origin "$tag"
  log "Actions: https://github.com/patsoft-dev/odoo-prod/actions"
}

unpushed_head_tags() {
  local tag tag_sha
  while IFS= read -r tag; do
    [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
    tag_sha=$(git rev-list -n 1 "$tag")
    [[ $tag_sha == "$(git rev-parse HEAD)" ]] || continue
    if git ls-remote --exit-code --tags origin "refs/tags/${tag}" >/dev/null 2>&1; then
      continue
    fi
    printf '%s\n' "$tag"
  done < <(git tag --points-at HEAD)
}

if [[ $push -eq 1 ]]; then
  if [[ $committed -eq 1 ]] || ! git merge-base --is-ancestor HEAD "origin/${require_branch}"; then
    log "==> push origin ${require_branch}"
    git push origin "HEAD:${require_branch}"
  fi
  if [[ $tagged -eq 1 ]]; then
    push_tag "$new_tag"
  else
    pushed_existing=0
    while IFS= read -r tag; do
      [[ -n $tag ]] || continue
      push_tag "$tag"
      pushed_existing=1
    done < <(unpushed_head_tags)
    if [[ $pushed_existing -eq 0 && $committed -eq 0 ]]; then
      log "nothing new to push"
    fi
  fi
else
  log
  if [[ $committed -eq 1 || $tagged -eq 1 ]]; then
    log "local only. Publish with:"
    if [[ $committed -eq 1 ]]; then
      log "  git push origin ${require_branch}"
    fi
    if [[ $tagged -eq 1 ]]; then
      log "  git push origin ${new_tag}"
    fi
    log "or re-run:  scripts/release.sh --push"
  fi
fi
