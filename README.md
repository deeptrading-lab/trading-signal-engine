# 🚀 Trading Signal Engine

AI 기반 주식 매매 신호 생성 및 자동매매 시스템

---

## 📌 Overview

Trading Signal Engine은 시장 데이터와 뉴스 데이터를 기반으로 **매수 / 매도 / 관망 신호를 생성**하고,  
분석 결과는 **매매 결정에 필요한 핵심 정보만 요약**해 전달합니다.

**MVP**에서는 별도 웹 프론트엔드 없이 **Slack으로 요약 알림**을 받아 확인하는 흐름을 우선합니다.  
웹 UI·승인 화면 등은 PRD에 포함되면 동일 프로세스로 구현합니다.

최종적으로는 **자동매매까지 확장 가능한 AI 시스템**을 목표로 합니다.

이 프로젝트는 단순한 매매 봇이 아니라,  
**AI 분석 + 의사결정 요약 레이어 + 규칙 기반 리스크 제어 + 실행 엔진**이 결합된 구조를 지향합니다.

---

## 🎯 Goals

- 시장 데이터 기반 기술적 분석
- 뉴스 기반 감정 및 이벤트 분석
- AI 기반 매매 의사결정 (BUY / SELL / HOLD)
- 종목별 핵심 의사결정 정보 요약 (MVP: **Slack 알림**)
- 판단 근거 리포트 자동 생성
- (향후) 승인 기반 반자동 매매 → 완전 자동매매 확장

---

## 🧠 Core Philosophy

> AI는 "판단"을 하고,  
> 시스템은 "통제"하며,  
> 엔진은 "실행"한다.

- LLM은 분석과 해석 담당
- Rule Engine은 리스크 관리 담당
- Trading Engine은 실제 주문 실행 담당

👉 **LLM이 직접 거래하지 않도록 설계 (안정성 확보)**

---

## 🤝 에이전트 역할 분리 (7인 체제)

요구사항부터 배포까지 역할을 나누어, 한 세션·한 대화 안에서도 **역할을 바꿔가며** 일관되게 수행하는 것을 전제로 합니다. 각 에이전트는 **서로를 견제하고 보완**하는 구조로 설계되어 있습니다.

| 역할 | 페르소나 및 책임 (Responsibility) | 특이 사항 |
|------|----------------------------------|-----------|
| **1. PM (기획)** | 비즈니스 가치 판단 및 PRD 작성 | 시장 상황과 비용(Cost) 고려 |
| **2. UX/UI 디자이너** | 유저 시나리오 설계 및 디자인 시스템 가이드 제공 | shadcn/ui 활용 등 |
| **3. Frontend Dev** | 디자이너의 가이드에 맞춰 UI 컴포넌트 구현 | 디자인 시스템 준수 여부 확인 |
| **4. Backend Dev** | 분석 로직 및 데이터 파이프라인 구현, 주문·리스크 엔진 구현 | Kotlin / Python 스택 전문성 |
| **5. QA (검증)** | PRD의 수용 기준(AC) 달성 여부 테스트 | 에지 케이스(예: 거래소 서버 다운) 테스트 |
| **6. Code Reviewer** | PR에 대한 코드 퀄리티 리뷰 및 머지 승인 | 클린 코드 및 아키텍처 패턴 감시 |
| **7. DevOps (배포)** | CI/CD 파이프라인 관리 및 운영 환경 모니터링 | 슬랙 알림 자동화 및 인프라 비용 체크 |

> 7개 역할은 항상 열려 있습니다. 특정 작업에 필요한 역할만 호출되며, PRD에서 요구하는 범위에 따라 누구든 먼저 합류할 수 있습니다.

### 흐름

```text
사용자 요구 → [PM] PRD
                ↓
         [UX/UI 디자이너] 시나리오·디자인 가이드 (UI 작업 시)
                ↓
         [Frontend Dev] UI 구현 / [Backend Dev] 로직·파이프라인 구현 + 한글 요약 커밋
                ↓
         [QA] PRD 기반 테스트 항목 정리 → 테스트 실행
                ↓
         [Code Reviewer] PR 리뷰 및 머지 승인
                ↓
         [DevOps] 유효한 커밋 시에만 push / 배포·모니터링
```

- **PM**은 코드 변경 없이 **PRD 품질**과 **비즈니스·비용 타당성**에 집중합니다.
- **UX/UI 디자이너**는 유저 시나리오와 디자인 시스템을 정의하고, Frontend Dev가 이를 따르도록 가이드합니다.
- **Frontend Dev / Backend Dev**는 PRD와 어긋나는 구현을 피하고, 커밋 메시지는 **한 줄~짧은 본문** 수준의 **한글 요약**을 권장합니다.
- **QA**는 PRD의 수용 기준을 **재현 가능한 검증 항목**으로 쪼개고, 에지 케이스까지 점검합니다.
- **Code Reviewer**는 클린 코드·아키텍처 패턴을 감시하고, 머지 승인 게이트 역할을 합니다.
- **DevOps**는 테스트·리뷰 정책에 맞게 “유효한 커밋”을 판단한 뒤에만 push·배포하고, 인프라 비용과 알림을 모니터링합니다.

절차·PRD 템플릿·커밋 규칙 등 **상세 규칙**은 [AGENTS.md](./AGENTS.md)를 따릅니다.

---

## 🏗️ System Architecture

```text
[MVP]
트리거 (스케줄 / 이벤트 / 수동 요청 등)
↓
API Gateway / BFF (또는 AI 서비스 직접 엔드포인트)
↓
┌──────────────────────────────┐
│ AI Analysis Service (Python) │
│ - GPT / Claude               │
│ - 뉴스 분석                    │
│ - 기술 분석                    │
│ - 신호 생성                    │
└──────────────────────────────┘
↓
┌──────────────────────────────┐
│ Notifications                │
│ - Slack (요약·신호·근거 알림)   │
└──────────────────────────────┘

[이후]
↓
┌──────────────────────────────┐
│ Trading Core (Kotlin)        │
│ - 리스크 검증                   │
│ - 주문 실행                    │
│ - 포지션 관리                   │
└──────────────────────────────┘
↓
Broker API (증권사)

Web Frontend — 의사결정 요약·승인 UI (PRD 포함 시 활성)
```

---

## 🤖 AI Architecture

### 🔹 GPT

- 최종 매매 판단 구조화
- 리포트 생성
- 에이전트 오케스트레이션

### 🔹 Claude

- 뉴스 요약
- 감정 분석
- 이벤트 해석

---

## 🔄 Workflow

1. 시장 데이터 수집
2. 뉴스 수집
3. 기술 분석
4. 뉴스 감정 분석
5. 신호 결합
6. 리스크 검증
7. 매수 / 매도 / 관망 결정
8. 리포트 생성
9. Slack으로 요약 알림 (MVP)
10. (향후) 사용자 승인 후 주문 실행

---

## 🧩 Project Structure

```text
trading-signal-engine/
│
├── backend/        # Kotlin Trading Core (실거래·리스크 단계)
├── ai/             # Python AI Analysis (LangGraph) + Slack 알림 연동
├── frontend/       # 웹 요약·승인 UI — PRD에 포함될 때 구현
├── infrastructure/ # AWS / Docker / Deployment
├── docs/           # Architecture / Design Docs
└── README.md
```

---

## 🛠️ Tech Stack

### Notifications (MVP)

- Slack (Incoming Webhooks 또는 Slack API / Bot)

### Frontend

- Next.js, TypeScript, React, shadcn/ui 등 — 웹 대시보드·승인 UI가 PRD에 포함될 때 적용

### Backend (Trading Engine)

- Kotlin
- Spring Boot
- Redis
- PostgreSQL

### AI / Analysis

- Python
- FastAPI
- LangGraph / LangChain
- OpenAI (GPT)
- Anthropic (Claude)

### Infrastructure

- AWS (EC2 / Lightsail)
- Docker
- Kubernetes (future)
- Prometheus / Grafana

---

## 💰 Cost Strategy

- 서버 비용: 약 $10 ~ $30 / 월
- AI 비용 포함 예상: 약 $20 ~ $80 / 월

👉 비용 절감 전략:

- 뉴스 캐싱
- 분석 주기 제한
- 종목 수 제한
- 이벤트 기반 분석

---

## ⚙️ Development Phases

### Phase 1: Analysis System

- 데이터 수집
- AI 분석
- 리포트 생성
- **Slack 알림** (신호·요약·핵심 근거)

### Phase 2: Paper Trading

- 가상 매매
- 성과 측정

### Phase 3: Semi-Automated Trading

- 사용자 승인 기반 매매

### Phase 4: Automated Trading

- 소액 자동매매
- 리스크 제한 기반 운영

---

## ⚠️ Risk Management

- 종목당 최대 투자 비율 제한
- 일일 손실 한도 제한
- 연속 손실 시 자동 중단
- 변동성 필터링
- 뉴스 신뢰도 필터

---

## 📊 Key Features (Planned)

- 💬 **Slack 알림**: 종목별 신호·요약·핵심 근거 (MVP)
- 📰 뉴스 기반 감정 분석
- 🤖 AI 매매 신호 생성
- 📄 자동 리포트 생성
- 🔎 웹 요약 뷰 / 승인 기반 매매 UI (PRD 포함 시)
- 📉 백테스트 엔진

---

## 🚧 Status

> 🚀 Initial Setup Phase

- [x] 프로젝트 설계
- [x] Git Repository 생성
- [ ] AI Analysis Service 구현
- [ ] Slack 알림 연동 (요약·신호)
- [ ] Trading Core 구현
- [ ] 웹 Decision Summary / 승인 UI (PRD 포함 시)
- [ ] Paper Trading
- [ ] 실거래 연동

---

## 🧑‍💻 Author

- DeepTrading Lab
