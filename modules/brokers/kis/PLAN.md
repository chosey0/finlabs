# KIS 실시간 시장 데이터 계획

## 범위

KIS SDK가 소유하는 WebSocket 연결, 인증, 구독 요청, 원시 메시지 파싱과
재연결 동작을 정의한다. 구독 목표 상태, Redis 발행, 저장과 캔들 집계는
[orchestration PLAN](../../orchestration/PLAN.md)이 소유한다.

## SDK 책임

- 국내·해외 실시간 체결과 10단계 호가 구독
- WebSocket 세션 연결, 정상 종료와 지수 백오프 재연결
- 브로커 원본 필드와 순서를 보존한 SDK 모델 반환
- CLI가 요청한 구독 추가·해제 명령 수행
- 연결 상태, 구독 성공·실패와 재연결 이벤트 노출

SDK는 Redis, PostgreSQL, Parquet, Rich, Discord를 import하지 않는다.

## 실시간 이벤트 필수 정보

- broker event type과 원본 식별자
- market, symbol과 venue
- exchange timestamp와 broker sequence
- trade 또는 10단계 orderbook payload
- 수신 시각은 SDK 외부 경계에서 추가할 수 있도록 원본 시각과 분리

canonical `event_id`, `received_seq`, 세션 분류와 저장용 필드 변환은
adapter/orchestration 계층에서 수행한다.

## 복구 정책

- 연결 단절 시 자동 재연결한다.
- 재연결 성공 후 PostgreSQL의 구독 목표 상태를 orchestration이 다시 전달한다.
- 부분 구독 실패는 성공한 구독과 분리해 보고한다.
- 구독 초기화는 이력을 삭제하지 않고 orchestration 명령에 따라 실제 구독만 해제한다.

## 완료 기준

- mock WebSocket으로 체결·호가 메시지 파싱을 검증한다.
- 연결 종료 후 백오프와 재연결 이벤트가 결정적으로 발생한다.
- 구독 추가·해제와 부분 실패가 구조화된 결과로 반환된다.
- SDK 경계 테스트가 다른 `modules.*` 형제 import를 거부한다.
