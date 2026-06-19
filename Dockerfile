FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config.yaml ./config.yaml

# Binance currently returns HTTP 400 for the liquidation-order endpoint on some hosts.
# Keep live snapshots running by treating liquidation data as optional until the data layer
# is migrated to a supported liquidation source.
RUN python - <<'PY'
from pathlib import Path

path = Path("src/crypto_flow_bot_v2/snapshot_builder.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from crypto_flow_bot_v2.binance.models import (",
    "from crypto_flow_bot_v2.binance.client import BinanceDataError\n"
    "from crypto_flow_bot_v2.binance.models import (",
)
text = text.replace(
    """        liquidation_orders = self._data_client.get_liquidation_orders(
            normalized_symbol,
            limit=derivatives_limit,
        )
""",
    """        try:
            liquidation_orders = self._data_client.get_liquidation_orders(
                normalized_symbol,
                limit=derivatives_limit,
            )
        except BinanceDataError:
            liquidation_orders = ()
""",
)
path.write_text(text, encoding="utf-8")
PY

RUN pip install --upgrade pip \
    && pip install .

RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "crypto_flow_bot_v2"]
