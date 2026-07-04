"""EndpointSpec registry for Kiwoom domestic industry REST APIs."""

from __future__ import annotations

from modules.brokers.kiwoom.endpoints.registry import EndpointSpec, register

ALL_INDEX = register(
    EndpointSpec(
        name="domestic.industry.all_index",
        method="POST",
        path="/api/dostk/sect",
        api_id="ka20003",
        supports_continuation=True,
    )
)

CODE_LIST = register(
    EndpointSpec(
        name="domestic.industry.code_list",
        method="POST",
        path="/api/dostk/stkinfo",
        api_id="ka10101",
        supports_continuation=True,
    )
)
