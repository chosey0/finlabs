<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# auth

## Purpose
Handles KIS REST OAuth token issuance, WebSocket approval key retrieval, and token cache abstraction. The module does not store tokens itself — instead it defines an abstract `TokenCache` protocol so callers can inject any backend (in-memory, file, or external storage).

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Bulk export: `IssuedToken`, `MemoryTokenCache`, `TokenCache`, `TokenRecord`, `issue_access_token[_async]`, `issue_websocket_approval_key[_async]`, `mask_sensitive_message`, `parse_token_response`, URL helpers |
| `cache.py` | `TokenRecord` (frozen, includes `is_expired()`), `TokenCache` Protocol, `MemoryTokenCache` default implementation |
| `oauth.py` | `IssuedToken` dataclass, `issue_access_token[_async]`, `issue_websocket_approval_key[_async]`, `parse_token_response`, `mask_sensitive_message`, `TOKEN_PATH`/`APPROVAL_PATH` constants, `SECRET_PATTERNS` masking regex |

## For AI Agents

### Working In This Directory
- Add new cache backends as separate classes implementing the `TokenCache` protocol (`get`/`set`/`delete`). Do not subclass `MemoryTokenCache`.
- `TokenRecord` is frozen — to refresh an expiry, discard the existing record and issue a new one via `set()`.
- Never log raw `app_key`, `app_secret`, `access_token`, or `approval_key`. All outgoing messages must pass through `mask_sensitive_message()`.
- The SDK does not enforce token refresh margins — that is the caller's responsibility.
- The synchronous (`issue_access_token`) and async (`issue_access_token_async`) APIs return identical payloads — modifying one without the other will cause a regression.

### Testing Requirements
- Verify token issuance using `httpx.MockTransport` to simulate KIS responses.
- `MemoryTokenCache` should have regression cases for both branches of `is_expired()` (before and after expiry).
- Regression for `mask_sensitive_message`: verify that app_key, app_secret, access_token, and approval_key patterns are masked.

### Common Patterns
- Cache key convention: REST token = `f"{environment}:{app_key}"`, WebSocket approval key = `f"ws:{environment}:{app_key}"` (created by `KisClient`).
- Approval key assumed valid for 24 hours — `KisClient.ensure_approval_key()` caches with `expires_at = now + 24h`.
- `parse_token_response` converts `expires_in` seconds to an `expires_at` datetime; raises `KisAuthError` if the field is missing.

## Dependencies

### Internal (within `modules.brokers.kis` only — no other `modules.*` sibling)
- `modules.brokers.kis.config` — `rest_base_url`
- `modules.brokers.kis.exceptions` — `KisAuthError`
- `modules.brokers.kis.types` — `Environment`

### External
- `httpx>=0.27.0` (async variants)
- stdlib: `re` (secret masking), `datetime`

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
