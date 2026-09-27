# 초기 설계 기준서

이 문서는 M1 구현이 시작되기 전까지 아키텍처, 위험 정책, 미확정 사항, 검증 기준의 단일 기준점입니다.

## 1. 아키텍처

### 목표

브로커 장애, 네트워크 타임아웃, 중복 이벤트, 프로세스 재시작 상황에서도 주문을 중복 실행하지 않고 전체 상태를 재구성할 수 있는 거래 엔진을 구축합니다.

### 구성 요소

1. `Signal`: 전략이 만든 관찰 가능한 입력과 판단 근거
2. `Proposal`: 주문 전 수량·가격·예상 비용 후보
3. `RiskDecision`: 승인·거절과 적용된 정책 버전
4. `RiskReservation`: 아직 체결되지 않은 주문의 위험·현금 예약
5. `OrderIntent`: 브로커 독립적인 주문 의도
6. `OutboxTask`: 브로커 호출을 위한 내구성 작업
7. `BrokerEventInbox`: 원본 브로커 이벤트의 멱등 수신함
8. `ExecutionActivity`·`ExecutionEntry`: append-only signed-delta 체결 원장
9. `PositionProjection`·`CashProjection`: 원장으로부터 재구성 가능한 조회 모델
10. `Reconciliation`: 로컬 상태와 브로커 상태의 불일치 조사·복구

### 트랜잭션 경계

위험 예약, 주문 의도, Outbox 기록은 하나의 로컬 데이터베이스 트랜잭션에서 처리합니다. 브로커 네트워크 호출은 이 트랜잭션이 커밋된 뒤 수행합니다.

### 멱등성과 fencing

- Signal에는 안정적인 멱등 키를 둡니다.
- 브로커 제출에는 재사용 가능한 `client_order_id`를 사용합니다.
- Outbox claim은 `claim_token`과 `claim_generation`을 발급합니다.
- 완료·실패·lease 연장은 현재 token과 generation이 일치할 때만 반영합니다.
- 갱신 행 수가 0이면 worker는 소유권을 잃은 것으로 처리합니다.

### 수치 저장

가격·수량·금액은 필드별 scale을 가진 signed 64-bit 정수 단위로 저장합니다. 입력은 `Decimal`, 정수 또는 검증된 문자열만 허용하고 `float`는 거부합니다.

## 2. 설계 결정

### 확정

- Python 3.12
- SQLite 기반 단일 프로세스 프로토타입
- 실제 브로커보다 `FakeBroker`를 먼저 구현
- 미국 주식·USD·현금 계좌·Long-only
- Market·Limit 주문만 1차 지원
- 정수 단위 저장과 UTC 시간 저장
- Outbox/Inbox 및 append-only signed-delta execution ledger
- Paper와 Live 환경의 구성·키·계좌·URL 완전 분리
- GitHub Actions는 테스트만 실행하며 주문 권한을 갖지 않음

초기 체결 원장은 회계적 복식부기가 아닙니다. 회계 목적의 복식부기가 필요할 때 `LedgerTransaction`과 `LedgerPosting`을 별도로 추가합니다.

### 연기

- PostgreSQL `SKIP LOCKED` 기반 다중 worker
- 운영 DB의 append-only 권한과 trigger
- 소수점 거래, 공매도, 마진, 장전·장후 거래
- 실제 브로커 adapter와 주문 상태 매핑

## 3. 위험 정책

- 모든 주문은 명시적인 `RiskDecision`을 거칩니다.
- 위험 한도를 계산할 수 없거나 데이터가 오래된 경우 주문을 거절합니다.
- 예약 가능한 현금과 포지션을 초과하는 주문을 거절합니다.
- 동일 Signal의 중복 주문을 차단합니다.
- 브로커 응답이 불명확하면 재제출보다 reconciliation을 우선합니다.
- Live 환경은 별도 승인과 명시적 환경 잠금 해제 없이는 시작하지 않습니다.

다음 상황에서는 신규 주문 제출을 차단합니다.

- 손실 한도 초과
- 시세 데이터 신선도 기준 미달
- 브로커·계좌 환경 불일치
- reconciliation 대기 작업 누적
- 원장과 브로커 상태의 설명되지 않은 차이
- 운영자가 수동 중지

수치 임계값은 아직 미확정입니다. 검증 통과를 위해 임계값을 완화하지 않으며, 실제 Paper 데이터를 기록한 뒤 승인받아 차단형 기준으로 전환합니다.

## 4. 미확정 사항

- 사용할 브로커와 공식 API
- 현금 계좌 또는 마진 계좌
- 소수점 거래 및 장전·장후 거래 지원 여부
- 주문당·종목당·계좌당 위험 한도
- 일일 손실 한도와 거래 중지 시간
- 킬스위치 발동·해제 권한
- 시세 공급자와 데이터 신선도 기준
- 수수료·환전·세금 모델
- Paper 검증 기간과 통과 기준
- 운영 알림 채널과 장애 대응 책임자

미확정 항목은 임의의 운영 기본값으로 확정하지 않습니다.

## 5. 인수 테스트

### Decimal 및 저장 단위

- `float`, NaN, Infinity 거부
- 허용 scale 초과 입력 거부
- signed 64-bit 경계값 저장과 범위 초과 거부
- 필드별 price·quantity·cash·fee scale 검증

### 주문 멱등성·장애 복구

- 동일 Signal 반복 처리 시 주문 의도 1개만 생성
- 동일 `client_order_id` 재호출 시 중복 주문 없음
- Outbox claim token·generation 불일치 완료 UPDATE 거부
- 브로커 제출 직후 프로세스 종료와 응답 유실 복구
- lease 만료 중 느린 worker와 새 worker 경합
- 조회 없음과 조회 실패 구분
- 재시작 후 미완료 주문 reconciliation

### 체결 원장

- 부분 체결 여러 건의 합계 재구성
- BUY/SELL 체결의 수량·현금 부호 검증
- Fill → Correction reversal → Corrected fill → Bust 재구성
- 이벤트 역순·중복 수신의 멱등 처리
- 기존 원장 행 UPDATE·DELETE 거부

테스트 이름과 실행 로그가 저장소에 남고, 확인되지 않은 항목은 통과로 표시하지 않습니다. FakeBroker 수직 흐름이 통과해도 Paper 또는 Live 준비 완료로 간주하지 않습니다.
