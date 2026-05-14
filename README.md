# FinLabs

FinLabs는 증권사 Open API를 파이썬 SDK 패키지 형태로 구현하고, 이를 기반으로 시장 데이터 수집·분석·시각화 하위 프로젝트를 구축하는 플랫폼입니다. 각 증권사 API는 독립적인 SDK 패키지로 제공되며, CLI·대시보드·분석 도구 등은 해당 SDK를 의존성으로 사용하는 별도 하위 프로젝트로 개발됩니다.

현재 구현은 한국투자증권(KIS) Open API SDK(`kis/`)와 이를 사용하는 시장 데이터 수집 CLI(`kis_cli/`)에 집중되어 있습니다.

## 구현된 SDK

| SDK | 증권사 | 설명 |
|-----|--------|------|
| [`kis/`](./kis/README.md) | 한국투자증권 (Korea Investment & Securities) | REST/WebSocket 클라이언트, 심볼·OHLCV 파서, 실시간 시세, 인증 |

## 하위 프로젝트

| 프로젝트 | 상태 | 설명 |
|----------|------|------|
| [`kis_cli/`](./kis_cli/README.md) | 구현됨 | KIS SDK 기반 시장 데이터 수집 CLI — 심볼 다운로드, OHLCV 수집, DuckDB 저장, 조회/내보내기 |
| 대시보드 | 미구현 (예정) | 수집된 시장 데이터 시각화 및 인터랙티브 차트 |
| 분석 | 미구현 (예정) | 통계 분석·팩터 연구·백테스트 도구 |
| 추가 증권사 SDK | 미구현 (예정) | 국내외 추가 증권사 Open API 연동 |

## 패키지 구조

```text
kis/       KIS SDK — REST/WebSocket 클라이언트, 엔드포인트 스펙, 파서, 모델
kis_cli/   FinLabs KIS CLI 애플리케이션 및 데이터 저장 워크플로
tests/     단위·통합 테스트
exports/   CSV 샘플 출력물
```
