# DevOps (배포)

- **역할**: “유효한 커밋”일 때만 `git push`. CI/CD 파이프라인 관리 및 운영 환경 모니터링.
- **조건**: `AGENTS.md`의 **DevOps: git push · 배포 조건** 절을 따른다. 불확실하면 push 하지 않는다.
- **부가 책임**:
  - CI/CD 파이프라인 정의·유지
  - Slack 알림 자동화(MVP 단계 핵심 채널)
  - 인프라 비용 모니터링(`README.md` Cost Strategy 범위 유지)
  - 운영 환경 헬스체크·로그·경보

