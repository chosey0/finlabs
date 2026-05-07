# config 패키지

`kis_cli.config`는 `kiscli`가 사용하는 로컬 설정, 프로필, 시크릿 참조 해석을 담당합니다. 설정 파일에는 시크릿 값을 직접 저장하지 않고 환경변수 참조만 저장합니다.

## 기본 경로

`paths.py`는 `platformdirs` 기반 경로를 제공합니다.

- `config_dir()`: 설정 디렉터리
- `cache_dir()`: 토큰 캐시 등 캐시 디렉터리
- `data_dir()`: SQLite DB 등 데이터 디렉터리
- `log_dir()`: 로그 디렉터리
- `default_config_file()`: 기본 `config.yaml` 경로

일반적인 기본 경로는 다음과 같습니다.

```text
~/.config/kis-cli/config.yaml
~/.cache/kis-cli/
~/.local/share/kis-cli/
```

## 설정 초기화

`init.py`는 `kiscli config init`에서 사용하는 설정 템플릿을 만듭니다.

```bash
kiscli config init
kiscli config init --profile mock --environment mock
kiscli config init --path ./config.yaml --force
```

생성되는 설정은 환경변수 참조를 사용합니다.

```yaml
active_profile: real

profiles:
  real:
    environment: real
    app_key: "${KIS_APP_KEY}"
    app_secret: "${KIS_APP_SECRET}"
    account_no: "${KIS_ACCOUNT_NO}"
    account_product_code: "${KIS_ACCOUNT_PRODUCT_CODE}"
```

## 프로필 관리

`profiles.py`는 대화형 프로필 추가/수정/삭제를 지원합니다.

```bash
kiscli config add
kiscli config update --profile csq1404
kiscli config delete --profile csq1404 --yes
```

프로필 시크릿은 `config.yaml`에 직접 들어가지 않고, 설정 파일과 같은 폴더의 `profiles.env`에 저장됩니다. `config.yaml`에는 프로필 UUID 앞 4자리 기반 참조가 기록됩니다.

```yaml
profiles:
  csq1404:
    id: 00000000-0000-0000-0000-000000000000
    environment: real
    expires_at: "2026-12-31"
    app_key: "$0000-{KIS_APP}"
    app_secret: "$0000-{KIS_SECRET}"
    owner: "$0000-{KIS_OWNER}"
    account_no: "$0000-{KIS_ACC_NO}"
```

## 프로필 해석과 검증

`resolver.py`는 `config.yaml`, `profiles.env`, 현재 프로세스 환경변수를 합쳐 최종 프로필 값을 해석합니다.

```bash
kiscli config validate
kiscli config validate --profile csq1404
kiscli config validate --path ./config.yaml
```

검증 시 확인하는 주요 필드는 다음과 같습니다.

- `id`
- `environment`
- `expires_at`
- `app_key`
- `app_secret`
- `owner`
- `account_no`

출력에서는 `mask_secret()`과 `mask_account()`로 민감 값을 마스킹합니다.

## 사용 예시

새 프로필을 만들고 인증을 확인하는 일반 흐름입니다.

```bash
kiscli config add
kiscli config validate --profile csq1404
kiscli auth test --profile csq1404
```

시크릿을 파일이 아닌 환경변수로 직접 제공하려면 `config init` 템플릿의 `${...}` 참조를 그대로 사용하면 됩니다.
