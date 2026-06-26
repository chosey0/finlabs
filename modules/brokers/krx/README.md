# KRX broker SDK

Pure async SDK for KRX Data Marketplace Open API index daily prices.

Supported index endpoints:

| Series | API ID | Guide |
| --- | --- | --- |
| KOSPI | `kospi_dd_trd` | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN |
| KOSDAQ | `kosdaq_dd_trd` | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=nimebcamqFNIPNcRrHoO |
| KRX | `krx_dd_trd` | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=SsgXTEspyJESKvyXZtCU |

Usage:

```python
from modules.brokers.krx import KrxClient

async with KrxClient.from_env() as client:
    rows = await client.indices.kospi_daily_prices(base_date="20200414")
```

`Credentials.from_env()` reads `KRX_AUTH_KEY`. The SDK does not load `.env`
files itself; callers should load environment files before constructing the
client when needed.
