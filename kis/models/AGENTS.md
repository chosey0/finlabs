<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# models

## Purpose
KIS API 응답을 정규화한 **frozen dataclass 모델** 모음입니다. 모든 모델은 `@dataclass(frozen=True)`로 immutable이며, `raw` 필드에 원본 페이로드를 보존해 디버깅·재파싱·미러링이 가능하게 합니다. 모델은 데이터만 보유하고 비즈니스 로직을 절대 포함하지 않습니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 모든 모델 일괄 export — `CurrentPrice`, `OhlcvBar`, `OverseasMinuteBar`, `OrderBookLevel`, `OrderBookSnapshot`, `RealtimeTick`, `SymbolRecord`, reference 모델들 |
| `quote.py` | `CurrentPrice` — 국내/해외 공용 현재가 스냅샷 (market, symbol, price, change, OHLV, volume, raw) |
| `ohlcv.py` | `OhlcvBar` (일/주/월/년 봉, interval 라벨 `1d`/`1w`/`1mo`/`1y`), `OverseasMinuteBar` (해외 분봉, 거래소 현지 시간 + KST 둘 다 보존) |
| `symbol.py` | `SymbolRecord` — 종목 마스터 항목 (국내/해외 공용), `with_downloaded_at()` 헬퍼 |
| `orderbook.py` | `OrderBookLevel` (호가 1 레벨), `OrderBookSnapshot` (지정가 호가 전체, exchange_ts/seq 포함) — Stage 4 추가 |
| `tick.py` | `RealtimeTick` — WebSocket 체결 틱 (price, volume, bid/ask) + `exchange_ts`/`seq` — Stage 4 추가 |
| `reference.py` | `ProductInfo`, `FinancialSummary`, `DomesticVolumeRankItem`, `OverseasVolumeSurgeItem`, `InvestorFlow` — Stage 5 reference/분석/순위 모델 |

## For AI Agents

### Working In This Directory
- **반드시** `@dataclass(frozen=True)`로 정의 — mutation은 SDK 디자인을 깨뜨립니다.
- 모든 모델은 `raw: dict[str, Any] = field(default_factory=dict)` 또는 `raw: dict[str, Any] | None = None`을 가집니다. 원본 페이로드 보존이 SDK 약속입니다.
- 금융 수치는 `Decimal | None` (없을 수 있는 값) 또는 `Decimal` (필수)로 표현합니다. `float`은 사용하지 마세요 (부동소수점 오차 회피).
- 수량은 `int | None` 또는 `int`, 시간은 KIS 문자열 그대로 유지하고 timezone 변환은 호출자에게 맡깁니다.
- 새 모델은 `__init__.py`의 `__all__`에 추가하고, 패키지 루트 `kis/__init__.py`에도 export합니다.

### Testing Requirements
- 모델 자체에는 거의 로직이 없으므로 테스트는 **파서** 쪽에서 인스턴스 생성을 검증합니다 (`tests/test_kis_package.py`, `tests/test_stage5_facades.py`).
- equality 기반 검증을 유지하려면 frozen + 모든 필드의 hashability를 깨지 않게 합니다 (dict 필드는 default_factory로 가능).

### Common Patterns
- 모델명은 의미 단위로 (`CurrentPrice`, `OhlcvBar`), 페이지네이션 리스트는 그냥 `list[Model]`로 반환하고 별도 컨테이너 모델을 만들지 않습니다.
- 국내/해외 공용 모델 (`CurrentPrice`, `OhlcvBar`, `SymbolRecord`)은 `market` 필드로 출처를 표시합니다.
- 실시간 모델 (`RealtimeTick`, `OrderBookSnapshot`)은 `received_seq`/`seq`를 모두 보유 — 큐 순서 보존용.

## Dependencies

### Internal
- 없음 (다른 `kis.*` 모듈을 import하지 않습니다 — 가장 하단 레이어).

### External
- stdlib: `dataclasses`, `decimal`, `typing`.

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
