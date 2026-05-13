<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# auth

## Purpose
KIS REST OAuth 토큰 발급과 WebSocket approval key 처리, 그리고 토큰 캐시 추상화를 담는 모듈입니다. 토큰 자체는 보관하지 않고, **추상 `TokenCache` 프로토콜**을 통해 호출자가 메모리/파일/외부 저장소 중 어느 백엔드든 주입할 수 있게 설계되어 있습니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `IssuedToken`, `MemoryTokenCache`, `TokenCache`, `TokenRecord`, `issue_access_token[_async]`, `issue_websocket_approval_key[_async]`, `mask_sensitive_message`, `parse_token_response`, URL 헬퍼 일괄 export |
| `cache.py` | `TokenRecord` (frozen, `is_expired()` 포함), `TokenCache` Protocol, `MemoryTokenCache` 기본 구현 |
| `oauth.py` | `IssuedToken` dataclass, `issue_access_token[_async]`, `issue_websocket_approval_key[_async]`, `parse_token_response`, `mask_sensitive_message`, `TOKEN_PATH`/`APPROVAL_PATH` 상수, `SECRET_PATTERNS` 마스킹 정규식 |

## For AI Agents

### Working In This Directory
- 새 캐시 백엔드는 `TokenCache` Protocol(`get`/`set`/`delete`)을 구현하는 별도 클래스로 추가하세요. `MemoryTokenCache`를 상속하지 마세요.
- `TokenRecord`는 frozen입니다 — 만료를 갱신하려면 기존 record를 폐기하고 새로 발급해 `set()`합니다.
- 로그에 절대 raw `app_key`, `app_secret`, `access_token`, `approval_key`를 노출하지 마세요. 모든 외부 메시지는 `mask_sensitive_message()`를 통과시킵니다.
- 토큰 만료 마진은 SDK가 강제하지 않습니다 — refresh margin은 호출자 (`kis_cli.core.token_cache.TOKEN_REFRESH_MARGIN` = 5분) 책임입니다.
- 동기 API(`issue_access_token`)와 비동기 API(`issue_access_token_async`)는 동일한 페이로드를 반환합니다 — 둘 중 하나만 수정하면 회귀가 생깁니다.

### Testing Requirements
- 토큰 발급은 `httpx.MockTransport`로 KIS 응답을 흉내내어 검증합니다.
- `MemoryTokenCache`는 `is_expired()` 분기 두 가지 (만료 전/후) 모두 회귀 케이스로 둡니다.
- `mask_sensitive_message` 회귀: app_key/app_secret/access_token/approval_key 패턴이 마스킹되는지 한 줄 검증.

### Common Patterns
- 캐시 키 컨벤션: REST 토큰은 `f"{environment}:{app_key}"`, WebSocket approval key는 `f"ws:{environment}:{app_key}"` (이 컨벤션은 `KisClient`가 만듭니다).
- approval key는 24시간 유효 가정 — `KisClient.ensure_approval_key()`가 `expires_at = now + 24h`로 캐시합니다.
- `parse_token_response`는 `expires_in` 초를 `expires_at` datetime으로 변환하고, 누락 시 `KisAuthError`를 던집니다.

## Dependencies

### Internal
- `kis.config` — `rest_base_url`
- `kis.exceptions` — `KisAuthError`
- `kis.types` — `Environment`

### External
- `httpx>=0.27.0` (`_async` 변형)
- stdlib: `re` (시크릿 마스킹), `datetime`

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
