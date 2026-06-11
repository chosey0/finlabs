# FinLabs

FinLabs는 증권사 Open API를 파이썬 SDK로 구현하고, 그 SDK를 기반으로 시장 데이터 수집·분석·시각화 도구를 확장해 나가는 오픈소스 개발자 도구 프로젝트입니다.

각 증권사 API는 독립적인 SDK 패키지로 분리하고, CLI·대시보드·분석 도구는 해당 SDK를 의존성으로 사용하는 별도 하위 프로젝트로 구성합니다. 목표는 증권사별 API 차이를 SDK 안에 캡슐화하고, 상위 도구에서는 일관된 방식으로 시장 데이터를 수집하고 활용할 수 있게 만드는 것입니다.

현재는 한국투자증권(KIS) Open API의 **해외주식 데이터 조회 SDK**와 이를 사용하는 시장 데이터 수집 CLI에 집중하고 있습니다. 국내주식 데이터 조회는 향후 Kiwoom REST API 기반 SDK로 별도 구현할 예정입니다.

코드베이스는 broker-agnostic한 계층형 코어(`modules/`)로 이전하는 중입니다. 사용자 진입점인 CLI 실행 방식(`python -m kis_cli`)은 그대로 유지되며, 변경되는 것은 내부 구조뿐입니다. 자세한 내부 아키텍처는 아래 [개발자용 아키텍처](#개발자용-아키텍처) 섹션을 참고하세요.

## 현재 구현 범위

| 영역 | 상태 | 설명 |
|------|------|------|
| [`modules/brokers/kis/`](./modules/brokers/kis/README.md) | 구현 중 | 한국투자증권 Open API SDK. 해외주식 REST/WebSocket 데이터 조회, 인증, 엔드포인트 스펙, 파서, 모델 제공 (이전 top-level `kis/`에서 이동 완료) |
| [`kis_cli/`](./kis_cli/README.md) | 구현 중 | KIS SDK 기반 CLI. 해외 심볼 다운로드, OHLCV·분봉 수집, DuckDB 저장, 조회/내보내기 제공 |
| `modules/` 계층형 코어 | 이전 중 | broker-agnostic 코어. SDK·warehouse read는 이동 완료, collection·write·config·job queue는 마이그레이션 진행 중 |
| `dashboard/` | 구현 중 | 수집된 시장 데이터를 읽어 시각화하는 Streamlit 대시보드 (`modules.orchestration`을 통해 조회) |
| Kiwoom SDK / adapter | 예정 | 국내주식 데이터 조회용 Kiwoom REST API SDK와 broker adapter |
| [`research/`](./research/README.md) | 초기 연구 | Candlestick VQ-VAE Tokenizer 중심의 시장 표현 학습 연구 |
| 분석 패키지 | 예정 | 수집된 시장 데이터 기반 통계 분석, 팩터 연구, 백테스트 도구 |

## 설계 원칙

- **SDK와 애플리케이션 분리**  
  증권사 API 인증, 요청, 응답 파싱은 SDK가 담당하고, 저장·CLI·설정·분석 워크플로는 별도 패키지가 담당합니다.

- **증권사별 SDK 독립성 유지**  
  한국투자증권, Kiwoom 등 각 증권사 API는 서로 다른 패키지로 구현합니다. 무리한 공통 추상화보다 각 API의 실제 동작과 제약을 명확히 반영합니다.

- **데이터 수집과 저장 우선**  
  초기 목표는 안정적인 시장 데이터 수집, 중복 방지 저장, 재현 가능한 조회입니다. 분석·대시보드는 그 위에 단계적으로 추가합니다.

- **민감 정보 보호**  
  API 키, 시크릿, 계좌번호, 토큰, 로컬 DB, 로그 파일은 소스 코드에 포함하지 않습니다.

## 저장소 구조

```text
finlabs/
├── modules/    # broker-agnostic 계층형 코어 (target architecture)
│   ├── brokers/kis/            # 한국투자증권 해외주식 데이터 조회 SDK (이전 top-level kis/)
│   ├── adapters/brokers/kis/   # SDK ↔ canonical 모델 변환 adapter
│   ├── orchestration/          # use case + warehouse-agnostic 조회
│   ├── domain/                 # canonical 데이터 계약 (I/O 없음)
│   └── storage/                # warehouse read repository
├── kis_cli/    # KIS SDK 기반 시장 데이터 수집 CLI (collection·write·config·job은 아직 여기 잔존)
├── dashboard/  # Streamlit 대시보드
├── research/   # 시장 표현 학습 및 tokenizer 연구
├── tests/      # 단위·통합 테스트
├── exports/    # CSV 샘플 출력물
├── AGENTS.md   # 에이전트 작업 가이드
└── README.md   # 프로젝트 개요
```

## 개발자용 아키텍처

내부 코어는 broker-agnostic한 4계층 스택으로 이전하는 중입니다. 의존성은 위에서 아래로만 흐릅니다.

```text
kis_cli / dashboard / research        # thin transport
        ↓
modules.orchestration                 # use case, 저장·로깅 조율 (쓰기는 여기서만)
        ↓
modules.adapters.brokers.{broker}     and  modules.storage
        ↓
modules.brokers.{broker}              # 순수 SDK (FinLabs 의존성 없음)

modules.domain   ← 모든 계층이 import 가능 (의존성 없음)
```

| 계층 | 위치 | 책임 |
|------|------|------|
| Broker SDK | `modules/brokers/{broker}/` | 순수 transport + 파싱. 다른 `modules.*` import 금지 |
| Broker adapter | `modules/adapters/brokers/{broker}/` | SDK 모델 → canonical `domain` 모델 변환. 저장 안 함 |
| Orchestration | `modules/orchestration/` | adapter + storage + 로깅을 하나의 작업으로 조율 |
| Domain | `modules/domain/` | canonical dataclass/Protocol, I/O 없음 |
| Storage (read) | `modules/storage/` | warehouse SQL의 단일 출처. 읽기는 `orchestration.query`를 통해서만 |

마이그레이션 현황:

- **이동 완료**: KIS SDK(`kis/` → `modules/brokers/kis/`), warehouse read query, KIS chart SDK 호출 일부의 adapter 이동
- **진행 중 (아직 `kis_cli`에 잔존)**: collection orchestration, storage write, config, job queue
- **예정**: 두 번째 broker(Kiwoom) SDK/adapter, `modules/config`로의 config 이전

계층 간 금지된 의존성은 `tests/architecture/test_boundaries.py`가 강제합니다.

## 개발 상태

이 저장소는 아직 초기 개발 단계입니다. PyPI 배포보다는 로컬 개발과 기능 검증을 우선하고 있습니다.

개발 환경에서는 `uv` 사용을 권장합니다.

```bash
uv sync
uv run python -m pytest
uv run ruff check .
```

CLI는 현재 로컬 개발 방식으로 실행합니다.

```bash
uv run python -m kis_cli --help
```

## 로드맵

1. KIS 해외주식 SDK 안정화
2. KIS CLI의 해외주식 데이터 수집·저장 워크플로 개선
3. Kiwoom REST API 기반 국내주식 SDK 추가
4. 공통 시장 데이터 모델과 저장소 구조 정리
5. Candlestick VQ-VAE Tokenizer 연구 구현
6. 분석 패키지 분리
7. 대시보드 패키지 분리

## 라이선스

아직 라이선스 파일은 추가하지 않았습니다.
