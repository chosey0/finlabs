# dashboard 패키지

`dashboard`는 Streamlit 기반 시장 데이터 대시보드입니다. 저장된 캔들을
조회하고, `research/fractal` 연구 기능을 노출합니다.

## 데이터 경로

```text
읽기: Streamlit(Chart/Fractal) -> modules.orchestration.query -> DuckDB
쓰기: Collect -> configured job server, if one is running
```

- `2_Chart`, `3_Fractal`은 warehouse를 직접 읽습니다.
- 읽기 SQL은 `modules.storage.repositories`가 단일 소스로 관리합니다.
- `1_Collect`는 선택적 job server의 HTTP 클라이언트입니다. 현재 저장소에는
  이 서버 구현이 포함되어 있지 않습니다.

읽기 페이지는 `dashboard/api_client.py`를 import하지 않습니다. 이 분리는
`tests/architecture/test_boundaries.py`가 정적으로 검사합니다.

## 실행

```bash
streamlit run dashboard/app.py
```

job server 주소는 환경변수로 지정할 수 있습니다.

```bash
export FINLABS_JOB_SERVER_HOST=127.0.0.1
export FINLABS_JOB_SERVER_PORT=8765
```

## 페이지

| 페이지 | 역할 | 데이터 경로 |
|--------|------|-------------|
| `1_Collect` | 수집 job 등록과 상태 조회 | configured HTTP server |
| `2_Chart` | 저장된 OHLCV candlestick 렌더 | warehouse 직접 |
| `3_Fractal` | fractal 파라미터 조절, 세그먼트 재계산, 렌더 | warehouse 직접 |
