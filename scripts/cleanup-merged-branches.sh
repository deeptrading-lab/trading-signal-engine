#!/usr/bin/env bash
# 머지 완료된 로컬 브랜치와 PR 체크아웃 ref를 정리한다.
#
# 사용법:
#   scripts/cleanup-merged-branches.sh          # 대화형 확인 후 삭제
#   scripts/cleanup-merged-branches.sh --yes    # 확인 없이 바로 삭제
#   scripts/cleanup-merged-branches.sh --dry-run  # 삭제 대상만 표시

set -euo pipefail

MAIN_BRANCH="${MAIN_BRANCH:-main}"
YES=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "알 수 없는 인자: $arg" >&2
      exit 2
      ;;
  esac
done

current="$(git symbolic-ref --short HEAD 2>/dev/null || echo '')"
if [[ "$current" != "$MAIN_BRANCH" ]]; then
  echo "경고: 현재 브랜치가 '$current' 이다. 안전하게 작업하려면 '$MAIN_BRANCH' 위에서 실행하자." >&2
  echo "계속하려면 먼저 'git checkout $MAIN_BRANCH' 후 재실행." >&2
  exit 1
fi

echo "1/3 원격 삭제된 ref 정리 (git fetch --prune)"
if [[ $DRY_RUN -eq 1 ]]; then
  git fetch --prune --dry-run
else
  git fetch --prune
fi

echo
echo "2/3 $MAIN_BRANCH 에 머지된 로컬 브랜치 탐색"
merged_branches="$(git branch --merged "$MAIN_BRANCH" \
  | sed 's/^[* ]*//' \
  | grep -Ev "^(\*|$MAIN_BRANCH|HEAD)$" \
  || true)"

if [[ -z "$merged_branches" ]]; then
  echo "  (정리할 머지된 브랜치 없음)"
else
  echo "$merged_branches" | sed 's/^/  - /'
fi

echo
echo "3/3 PR 체크아웃 ref 탐색 (pr-*)"
pr_refs="$(git branch --list 'pr-*' | sed 's/^[* ]*//' || true)"
if [[ -z "$pr_refs" ]]; then
  echo "  (정리할 pr-* ref 없음)"
else
  echo "$pr_refs" | sed 's/^/  - /'
fi

all_targets="$(printf '%s\n%s\n' "$merged_branches" "$pr_refs" | grep -v '^$' || true)"
if [[ -z "$all_targets" ]]; then
  echo
  echo "정리할 대상 없음. 종료."
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "--dry-run 모드: 실제 삭제는 수행하지 않음."
  exit 0
fi

echo
if [[ $YES -eq 0 ]]; then
  read -r -p "위 브랜치들을 삭제할까? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "취소."; exit 0 ;;
  esac
fi

echo
while IFS= read -r branch; do
  [[ -z "$branch" ]] && continue
  # pr-* 는 보통 origin/pull/N/head fetch로만 만들어지므로 강제 삭제(-D) 허용.
  # 그 외 머지된 브랜치는 안전 삭제(-d) 후, 혹시 남아있는 변경이 있으면 사용자가 직접 판단.
  if [[ "$branch" == pr-* ]]; then
    git branch -D "$branch"
  else
    git branch -d "$branch"
  fi
done <<< "$all_targets"

echo
echo "완료."
