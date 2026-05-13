<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# overseas (endpoints)

## Purpose
해외 거래소(NAS/NYS/AMS/HKS/TSE/SHS/SZS/HNX/HSX) KIS Open API의 **EndpointSpec 등록 모듈** 모음입니다. 국내와 달리 KIS는 해외 endpoint 대부분에 모의투자 TR ID를 제공하지 않으므로, 등록된 spec 대다수가 `tr_id_mock=None`이고 `environment="mock"` 사용 시 `MockNotSupportedError`가 자동 발생합니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `analysis`, `basic_quote`, `realtime` 서브모듈을 import해 spec 등록 트리거 |
| `basic_quote.py` | `[해외주식] 기본시세.xlsx` — `overseas.price.current` (HHDFS00000300, mock=None), `overseas.chart.ohlcv` (FHKST03030100, mock=None), `overseas.chart.dailyprice` (HHDFS76240000, `supports_tr_cont=True`), `overseas.chart.minute` (HHDFS76950200) |
| `analysis.py` | `[해외주식] 시세분석.xlsx` — `overseas.analysis.price_fluct` (HHDFS76260000), `volume_surge` (HHDFS76270000), `volume_power`, `updown_rate`, `new_highlow`, `trade_vol` 등 (대량 spec, 모두 mock=None) |
| `realtime.py` | `[해외주식] 실시간시세.xlsx` — `overseas.realtime.trades` (HDFSCNT0, WebSocket, mock=None), `overseas.realtime.orderbook` (HDFSASP0, mock=None) |

## For AI Agents

### Working In This Directory
- **거의 모든 해외 endpoint는 `tr_id_mock=None`** 입니다. KIS 문서를 확인해서 진짜로 mock 미지원인지 확인 후 등록하세요 — 임의로 `None`을 채우면 안 됩니다.
- 이름 컨벤션: `overseas.<group>.<action>` (e.g. `overseas.price.current`, `overseas.chart.minute`, `overseas.analysis.volume_surge`).
- 등록 패턴은 국내와 동일:
  - 핵심 endpoint는 모듈 변수로 노출 (`CURRENT_PRICE = register(EndpointSpec(...))`).
  - 대량 spec은 `_SPECS = (...,)` 튜플 + 루프.
- 해외 분석 endpoint는 `required_params`로 `AUTH`, `EXCD`, `GUBN`, `NDAY`, `VOL_RANG` 같은 KIS 특유 키를 받습니다. 키 이름 그대로 등록하세요 (KIS는 대소문자/언더스코어가 엄격합니다).
- `overseas.chart.minute`처럼 페이지네이션이 KIS 응답 본문(`output1.next`)에 의존하는 경우는 `supports_tr_cont=False`로 두고, 호출자(`kis/overseas/chart.py`)에서 본문 기반 분기를 구현합니다.

### Testing Requirements
- mock-unsupported endpoint는 `tr_id_for("mock")` 호출 시 `MockNotSupportedError` 발생을 회귀 한 줄 확인 (`tests/test_kis_package.py`).
- 핵심 endpoint(`overseas.price.current`, `overseas.chart.dailyprice`, `overseas.chart.minute`)는 `lookup(...)`로 메타데이터를 가져와 `tr_id_real`/`path` 일치 여부 검증.

### Common Patterns
- 모듈 docstring 첫 줄에 원본 엑셀 워크북명을 명시 (`"""EndpointSpec registry for `[해외주식] 기본시세.xlsx`."""`).
- WebSocket endpoint는 국내와 동일하게 `method="POST"` + WebSocket 헤더 5종 + `required_params=("tr_id", "tr_key")`.
- 해외 거래소 코드(`EXCD`)는 KIS 정의대로 3글자 대문자 (`NAS`/`NYS`/`AMS`/`HKS`/`TSE`/`SHS`/`SZS`/`HNX`/`HSX`).

## Dependencies

### Internal
- `kis.endpoints.registry` — `EndpointSpec`, `register`

### External
- 없음.

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
