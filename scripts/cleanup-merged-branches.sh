#!/usr/bin/env bash
# 머지 완료된 로컬 브랜치와 PR 체크아웃 ref를 정리한다.
#
# 감지 범위:
#   - true merge / fast-forward: git merge-base --is-ancestor 로 판정
#   - squash / rebase merge:     branch tip 의 tree sha 가 main 히스토리에 있는지로 판정
#   - pr-* ref:                  QA/Reviewer가 fetch로 만든 임시 ref
#
# 사용법:
#   scripts/cleanup-merged-branches.sh            # 대화형 확인 후 삭제
#   scripts/cleanup-merged-branches.sh --yes      # 확인 없이 바로 삭제
#   scripts/cleanup-merged-branches.sh --dry-run  # 삭제 대상만 표시

set -eo pipefail
# macOS 기본 bash 3.2 에서 `${array[@]}` 로 빈 배열 전개가 unbound variable 로 터지므로 -u 는 쓰지 않는다.

MAIN_BRANCH="${MAIN_BRANCH:-main}"
YES=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,13p' "$0"
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
echo "2/3 $MAIN_BRANCH 에 머지된 로컬 브랜치 탐색 (true/squash/rebase)"

# 핵심 알고리즘: 브랜치 tip 의 tree sha 가 main 히스토리 어딘가에 있으면 머지된 것.
# - true merge / fast-forward → branch tip 이 main 의 조상 (is-ancestor 로 먼저 잡힘)
# - squash merge → main 의 squash 커밋 tree 가 branch tip tree 와 정확히 일치
# - rebase merge → main 의 rebase 커밋 tree 들 중 하나가 branch tip tree 와 일치
# tree sha 충돌은 현실적으로 0 이라 오탐 없음.

true_merged=()
squash_merged=()

# main 히스토리의 모든 tree sha 를 한 번만 수집해 O(N) 비교 준비
main_trees="$(git log "$MAIN_BRANCH" --format='%T')"

# pr-* 를 제외한 로컬 브랜치를 순회하며 머지 여부 판정
while IFS= read -r branch; do
  [[ -z "$branch" ]] && continue
  # true merge / fast-forward
  if git merge-base --is-ancestor "$branch" "$MAIN_BRANCH" 2>/dev/null; then
    true_merged+=("$branch")
    continue
  fi
  # squash / rebase merge: 브랜치 tip tree 가 main 히스토리에 있는가?
  branch_tree="$(git rev-parse "$branch^{tree}" 2>/dev/null || true)"
  if [[ -n "$branch_tree" ]] && grep -Fxq "$branch_tree" <<< "$main_trees"; then
    squash_merged+=("$branch")
  fi
done < <(git branch --list \
  | sed 's/^[* ]*//' \
  | grep -Ev "^(\*|$MAIN_BRANCH|HEAD)$" \
  | grep -Ev '^pr-')

if [[ ${#true_merged[@]} -eq 0 && ${#squash_merged[@]} -eq 0 ]]; then
  echo "  (정리할 머지된 브랜치 없음)"
else
  for b in "${true_merged[@]}"; do
    echo "  - $b  (true merge)"
  done
  for b in "${squash_merged[@]}"; do
    echo "  - $b  (squash/rebase merge)"
  done
fi

echo
echo "3/3 PR 체크아웃 ref 탐색 (pr-*)"
pr_refs=()
while IFS= read -r ref; do
  [[ -z "$ref" ]] && continue
  pr_refs+=("$ref")
done < <(git branch --list 'pr-*' | sed 's/^[* ]*//')

if [[ ${#pr_refs[@]} -eq 0 ]]; then
  echo "  (정리할 pr-* ref 없음)"
else
  for r in "${pr_refs[@]}"; do
    echo "  - $r"
  done
fi

total=$(( ${#true_merged[@]} + ${#squash_merged[@]} + ${#pr_refs[@]} ))
if [[ $total -eq 0 ]]; then
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
# true merge 는 git 이 "merged" 로 인지하므로 안전 삭제(-d) 사용
for branch in "${true_merged[@]}"; do
  git branch -d "$branch"
done
# squash/rebase 머지는 git 이 "not merged" 로 보므로 강제 삭제(-D) 필요
for branch in "${squash_merged[@]}"; do
  git branch -D "$branch"
done
# pr-* 는 임시 fetch ref 라 강제 삭제(-D)
for ref in "${pr_refs[@]}"; do
  git branch -D "$ref"
done

echo
echo "완료."
