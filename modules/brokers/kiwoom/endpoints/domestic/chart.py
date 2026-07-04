"""EndpointSpec registry for Kiwoom domestic stock chart REST APIs."""

from __future__ import annotations

from modules.brokers.kiwoom.endpoints.registry import EndpointSpec, register

TICK = register(
    EndpointSpec(
        name="domestic.chart.tick",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10079",
        supports_continuation=True,
    )
)

MINUTE = register(
    EndpointSpec(
        name="domestic.chart.minute",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10080",
        supports_continuation=True,
    )
)

INDUSTRY_TICK = register(
    EndpointSpec(
        name="domestic.chart.industry_tick",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka20004",
        supports_continuation=True,
    )
)

INDUSTRY_MINUTE = register(
    EndpointSpec(
        name="domestic.chart.industry_minute",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka20005",
        supports_continuation=True,
    )
)

INDUSTRY_DAILY = register(
    EndpointSpec(
        name="domestic.chart.industry_daily",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka20006",
        supports_continuation=True,
    )
)

INDUSTRY_WEEKLY = register(
    EndpointSpec(
        name="domestic.chart.industry_weekly",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka20007",
        supports_continuation=True,
    )
)

INDUSTRY_MONTHLY = register(
    EndpointSpec(
        name="domestic.chart.industry_monthly",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka20008",
        supports_continuation=True,
    )
)

DAILY = register(
    EndpointSpec(
        name="domestic.chart.daily",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10081",
        supports_continuation=True,
    )
)

WEEKLY = register(
    EndpointSpec(
        name="domestic.chart.weekly",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10082",
        supports_continuation=True,
    )
)

MONTHLY = register(
    EndpointSpec(
        name="domestic.chart.monthly",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10083",
        supports_continuation=True,
    )
)

YEARLY = register(
    EndpointSpec(
        name="domestic.chart.yearly",
        method="POST",
        path="/api/dostk/chart",
        api_id="ka10094",
        supports_continuation=True,
    )
)
