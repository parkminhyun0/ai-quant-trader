# AI Quant Trader

안전성, 재현성, 감사 가능성을 우선하는 AI 기반 주식 자동매매 시스템입니다.

> [!IMPORTANT]
> 현재 단계는 `FakeBroker`와 SQLite를 사용하는 연구·검증 단계입니다. 실제 주문을 실행하지 않으며, 실거래 전에는 별도의 승인·Paper 검증·킬스위치가 필요합니다.

## 현재 범위

- 미국 주식, USD 현금 계좌, Long-only
- 정규장, Market·Limit 주문
- 소수점·공매도·마진 제외
- SQLite 단일 주문 worker와 단일 이벤트 worker
- 브로커 미확정 상태의 `FakeBroker` 수직 흐름

## 핵심 흐름

```text
Signal
→ Proposal
→ RiskDecision
→ Reservation + Intent + Outbox
→ Broker Adapter
→ Event Inbox / REST Observation
→ Execution Ledger
→ Position·Cash Projection
→ Reconciliation
```

## 안전 원칙

- 전략은 브로커나 데이터베이스를 직접 호출하지 않습니다.
- 위험 승인 뒤에만 주문 의도를 생성합니다.
- 예약·주문 의도·Outbox는 하나의 데이터베이스 트랜잭션으로 기록합니다.
- 브로커 호출은 데이터베이스 트랜잭션 밖에서 수행합니다.
- 응답이 불명확한 주문은 즉시 재전송하지 않고 재조정합니다.
- 금액·가격·수량에 `float`를 사용하지 않습니다.
- 실제 비밀키와 계좌정보는 저장소에 커밋하지 않습니다.
- Paper와 Live의 키·계좌·URL을 완전히 분리합니다.

## 첫 번째 마일스톤

`M1 · FakeBroker 주문 수직 흐름`

완료 기준은 Signal 한 건이 위험 심사, 주문 의도, Outbox, FakeBroker 제출, 이벤트 Inbox, 체결 원장, 현금·포지션 projection까지 통과하고 중복·중단 상황에서 안전하게 복구되는 것입니다.

## 시가총액 대시보드

국내와 미국 주식을 분리하여 시가총액 상위 100개를 표시하는 읽기 전용 화면을 제공합니다. 한국투자 Open API 키를 서버 환경변수로 설정하면 국내 KRX와 미국 NYSE·NASDAQ·AMEX 순위를 조회합니다.

```bash
uvicorn ai_quant_trader.web.app:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. 키가 없으면 연결 안내가 표시되며, UI 확인이 필요할 때만 `MARKET_DATA_DEMO=true`를 사용합니다. 데모 데이터는 실제 시세가 아닙니다.

## 문서

- [초기 설계 기준서](PROJECT_SPEC.md)

## 상태

- 저장소 초기화: 진행 중
- 실제 브로커 연결: 미구현
- Paper 거래: 미검증
- Live 거래: 금지
