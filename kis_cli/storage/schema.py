from __future__ import annotations

from kis_cli.storage.warehouse import WAREHOUSE_TABLE_NAMES, create_warehouse_schema

TABLE_NAMES = WAREHOUSE_TABLE_NAMES


def create_schema(connection) -> None:
    create_warehouse_schema(connection)
