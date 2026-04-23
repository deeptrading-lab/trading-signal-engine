# 🚀 Trading Signal Engine

AI 기반 주식 매매 신호 생성 및 자동매매 시스템

---

## 📌 Overview

Trading Signal Engine은 시장 데이터와 뉴스 데이터를 기반으로 **매수 / 매도 / 관망 신호를 생성**하고,  
특정 종목 분석 요청 시 **매매 결정에 필요한 핵심 정보만 요약해 가시성 있게 제공**하며,  
최종적으로는 **자동매매까지 확장 가능한 AI 시스템**입니다.

이 프로젝트는 단순한 매매 봇이 아니라,  
**AI 분석 + 의사결정 요약 레이어 + 규칙 기반 리스크 제어 + 실행 엔진**이 결합된 구조를 지향합니다.

---

## 🎯 Goals

- 시장 데이터 기반 기술적 분석
- 뉴스 기반 감정 및 이벤트 분석
- AI 기반 매매 의사결정 (BUY / SELL / HOLD)
- 종목별 핵심 의사결정 정보 요약 노출
- 판단 근거 리포트 자동 생성
- 승인 기반 반자동 매매 → 완전 자동매매 확장

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

## 🏗️ System Architecture

```text
User (Symbol Request / Approval UI)
↓
Frontend (Decision Summary UI)
↓
API Gateway / BFF
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
│ Trading Core (Kotlin)        │
│ - 리스크 검증                   │
│ - 주문 실행                    │
│ - 포지션 관리                   │
└──────────────────────────────┘
↓
Broker API (증권사)
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
9. (옵션) 사용자 승인
10. 주문 실행

---

## 🧩 Project Structure

```text
trading-signal-engine/
│
├── backend/        # Kotlin Trading Core
├── ai/             # Python AI Analysis (LangGraph)
├── frontend/       # 종목 분석 요청/요약/승인 UI
├── infrastructure/ # AWS / Docker / Deployment
├── docs/           # Architecture / Design Docs
└── README.md
```

---

## 🛠️ Tech Stack

### Frontend

- Next.js
- TypeScript
- React
- shadcn/ui

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

- 🔎 종목 분석 요청 기반 요약 뷰
- 🧾 매매 결정 핵심 지표 카드형 노출
- 📰 뉴스 기반 감정 분석
- 🤖 AI 매매 신호 생성
- 📄 자동 리포트 생성
- ✅ 승인 기반 매매 시스템
- 📉 백테스트 엔진

---

## 🚧 Status

> 🚀 Initial Setup Phase

- [x] 프로젝트 설계
- [x] Git Repository 생성
- [ ] AI Analysis Service 구현
- [ ] Trading Core 구현
- [ ] Decision Summary UI 개발
- [ ] Paper Trading
- [ ] 실거래 연동

---

## 🧑‍💻 Author

- DeepTrading Lab
