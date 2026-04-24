---
name: spring-api
description: Spring Boot REST API 관례 (Trading Core 백엔드)
---

# Spring API (Trading Core)

- 컨트롤러는 얇게: 검증·매핑·위임. 비즈니스 규칙은 서비스/도메인 계층.
- 요청/응답 DTO와 도메인 모델 분리. 외부(브로커) DTO와 내부 도메인 혼용 금지.
- 예외는 공통 핸들러로 일관된 본문(코드·메시지)으로 응답.
- 설정·시크릿은 코드에 하드코딩하지 않는다.
