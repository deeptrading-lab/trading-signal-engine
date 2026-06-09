# PRD: Market Data Engine Rebuild

## 1. 배경 / 문제

현재 저장소에는 OpenAI 뉴스 수집·분석, 비트코인 신호, Slack coordinator,
SQLite 기반 점수 집계가 함께 존재한다. 새 제품 방향에서 Engine은 판단이나 분석을
수행하지 않고, AWS에서 장시간 실행되는 데이터 인프라로 한정한다.

Engine의 책임은 다음 두 가지다.

1. 다른 서비스가 만든 뉴스·분석 결과를 Supabase에 CRUD한다.
2. 한국투자증권(KIS) API와 연결해 종목 시세, 거래량, 분봉, 일봉·주봉을 수집하고
   실시간 WebSocket 스트림을 내부 클라이언트에 중계한다.

기존 기능이 재사용 가능하더라도 이 책임과 직접 관계가 없으면 제거한다.

## 2. 목표

- Engine 프로세스가 LLM 또는 투자 판단 없이 데이터 저장·조회·스트림만 담당한다.
- Supabase를 운영 저장소의 단일 기준으로 사용한다.
- KIS REST API로 과거 캔들을 동기화하고 KIS WebSocket으로 실시간 체결을 수신한다.
- 실시간 체결을 저장하고 1분봉으로 집계하며 연결된 Engine WebSocket 클라이언트에
  동일 이벤트를 중계한다.
- AWS 컨테이너 환경에서 환경변수만으로 실행할 수 있다.

## 3. 범위 (In scope)

### 3.1 유지·재작성

- Python HTTP/WebSocket 서버
- Supabase backend credential을 사용하는 repository 경계
- `/health` 상태 확인
- `.env.local` 로컬 설정과 배포 환경변수 설정

### 3.2 추가

- 종목 CRUD
- 외부 분석 결과 CRUD
  - Engine은 `payload` JSON을 해석하거나 점수화하지 않는다.
- 저장된 tick/candle 조회 API
- KIS OAuth access token 및 WebSocket approval key 발급
- KIS 국내주식 기간별 시세 API
  - 일봉, 주봉, 월봉
- KIS 국내주식 당일 분봉 API
- KIS 국내주식 실시간 체결가(`H0STCNT0`) 구독
- bounded queue 기반 tick/candle batch 저장, 1분봉 집계/upsert, WebSocket broadcast
- 재연결 backoff와 health 상태 노출
- Supabase migration과 RLS
- Docker/App Runner 실행 경로

### 3.3 제거

- OpenAI/Anthropic API 호출과 비용 계산
- 뉴스 검색·요약·감성/영향/관련도 점수화
- Bitcoin allocation 및 매수·매도 신호
- 기술 지표·추천 가격·추천 수량
- Slack coordinator와 관련 인증·compliance
- 기존 SQLite 뉴스 저장소
- 기존 뉴스 전용 API, CLI, scheduler 후보
- 위 기능만을 위한 테스트·PRD·QA·환경변수·의존성

## 4. 비범위 (Out of scope)

- 주문, 정정, 취소, 계좌·잔고 관리
- 매수/매도 판단 및 전략 실행
- 뉴스 수집 또는 LLM 분석
- 과거 전체 분봉 백필
  - KIS 당일 분봉 API가 제공하는 범위만 지원한다.
- 여러 Engine 인스턴스 간 WebSocket subscription 조정
- Supabase Realtime을 프론트엔드에 직접 노출
- 거래소 시세의 제3자 재배포 권한 판단

## 5. 수용 기준

1. 앱 시작 시 OpenAI, Anthropic, Slack 설정 없이 정상 기동한다.
2. 인증된 호출자가 종목과 외부 분석 결과를 생성·조회·수정·삭제할 수 있다.
3. 분석 결과의 `payload`는 임의 JSON으로 저장되며 Engine이 내용을 변경하지 않는다.
4. 캔들 동기화 요청에서 `1m`, `1d`, `1w`, `1mo`를 구분하고 KIS 응답을
   공통 candle schema로 저장한다.
5. stream이 활성화되면 enabled 종목의 `H0STCNT0` 체결을 수신해 tick을 저장한다.
6. 같은 분의 체결은 하나의 1분봉으로 집계되어 upsert된다.
7. `/ws/market` 연결은 수신 tick/candle 이벤트를 JSON으로 받는다.
8. KIS 연결 실패 시 프로세스가 종료되지 않고 제한된 exponential backoff로 재연결한다.
9. `/health`가 DB backend, KIS stream 활성 여부, 마지막 이벤트/오류를 반환한다.
10. backend write token이 없거나 틀린 변경 요청은 `401`을 반환한다.
11. Supabase RLS가 활성화되고 public policy는 생성하지 않는다.
12. 저장소에 LLM/Slack/Bitcoin/news-scoring 런타임 코드와 의존성이 남지 않는다.

## 6. 가정·제약

- Python 3.12, FastAPI, httpx, websockets를 사용한다.
- 운영 DB는 Supabase Postgres이며 Engine은 backend secret만 사용한다.
- KIS 시세 이용·표출·재배포는 계정과 계약 조건을 준수해야 한다.
- KIS key, Supabase secret, Engine write token은 AWS secret 환경변수로만 주입한다.
- 초기 구현은 단일 Engine 인스턴스를 기준으로 한다.

## 7. 참고

- KIS 공식 샘플: `koreainvestment/open-trading-api`
- KIS 기간별 시세: `inquire-daily-itemchartprice`, TR `FHKST03010100`
- KIS 당일 분봉: `inquire-time-itemchartprice`, TR `FHKST03010200`
- KIS 실시간 체결: `H0STCNT0`
- 구현 패키지: `ai/market_data_engine`
