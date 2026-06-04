"""Run the job server: ``python -m kis_cli.server``.

Binds to localhost only (see ``kis_cli.server.config``). This is the single
process that holds KIS credentials.
"""

from __future__ import annotations

import ipaddress

import uvicorn

from kis_cli.server.app import create_app
from kis_cli.server.config import SERVER_HOST, SERVER_PORT


def _is_loopback(host: str) -> bool:
    if host.lower() in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    if not _is_loopback(SERVER_HOST):
        raise SystemExit(
            f"Refusing to bind {SERVER_HOST}: the job server holds KIS credentials and "
            "has no authentication, so it must stay on loopback. Unset KIS_SERVER_HOST "
            "or set it to 127.0.0.1/localhost."
        )
    uvicorn.run(create_app(), host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
