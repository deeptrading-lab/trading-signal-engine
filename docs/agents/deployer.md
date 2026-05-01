# DevOps (배포)

- **역할**: “유효한 커밋”일 때만 `git push`. CI/CD 파이프라인 관리 및 운영 환경 모니터링.
- **조건**: `AGENTS.md`의 **DevOps: git push · 배포 조건** 절을 따른다. 불확실하면 push 하지 않는다.
- **부가 책임**:
  - CI/CD 파이프라인 정의·유지
  - Slack 알림 자동화(MVP 단계 핵심 채널)
  - 인프라 비용 모니터링(`README.md` Cost Strategy 범위 유지)
  - 운영 환경 헬스체크·로그·경보
  - **후속 이슈 등록**: 머지 시점에 리뷰어/QA가 트래킹 권고한 후속 작업을 GitHub Issue로 등록한다. 등록 절차는 `AGENTS.md`의 **이슈 우선순위 (P0/P1/P2)** 절을 따른다(기존 이슈 스캐닝 → priority 평가 → 라벨 부여 → 출처 명시).

