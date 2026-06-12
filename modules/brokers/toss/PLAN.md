# Toss 장 운영 정보 계획

## 범위

Toss 국내·해외 장 운영 정보 API의 순수 SDK와 canonical calendar adapter를
구현한다. 동기화 스케줄과 PostgreSQL 저장은 orchestration/storage가 소유한다.

## SDK

- `modules/brokers/toss/market_info.py`에서 국내·해외 장 운영 정보 API 호출
- 공식 OpenAPI 계약에 따른 요청, 응답 모델과 파싱
- 인증, HTTP 오류와 응답 오류를 SDK 예외로 노출
- FinLabs domain, storage와 orchestration을 import하지 않음

공식 API:

- 국내: `getkrmarketcalendar`
- 해외: `getusmarketcalendar`
- 계약 원본: `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json`

## Adapter

- `modules/adapters/brokers/toss/calendar.py`에서 canonical 장 운영 모델로 변환
- 국내·해외 market/venue 코드 정규화
- 거래일, 세션 시작·종료와 휴장 상태 변환
- 브로커 응답 누락값을 임의 추정하지 않음

## 동기화 정책

- 매일 06:00 KST에 과거 30일과 미래 1년을 동기화한다.
- PostgreSQL 수동 override가 가장 높은 우선순위를 갖는다.
- Toss 실패 시 검증된 라이브러리를 fallback으로 사용한다.
- 해결할 수 없는 값은 `unknown`으로 기록한다.
- 동기화 실패 시 기존 값을 보존하고 변경 이력을 기록한다.
- 확정된 장 정보로 기존 `unknown` 세션을 재분류한다.

## 완료 기준

- 실제 API를 호출하지 않는 fixture 기반 SDK/adapter 테스트가 통과한다.
- 국내·해외 정상 응답, 누락 필드와 오류 응답을 검증한다.
- override, Toss, fallback, unknown 우선순위가 결정적으로 적용된다.
