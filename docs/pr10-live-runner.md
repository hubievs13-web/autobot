# PR 10 — Live Telegram-only alert runner

PR 10 connects the already-merged PR 2–PR 8 components into one live polling loop.

## Included

- `LiveAlertRunner` orchestration layer.
- Production stack construction from config:
  - public Binance USDⓈ-M Futures REST client
  - `MarketSnapshotBuilder`
  - `RFAEngine`
  - in-memory `VirtualPositionManager`
  - `TelegramAlertService`
- One polling cycle per configured symbol.
- Per-symbol error isolation: one failed snapshot build does not stop other symbols.
- Full Telegram signal alert only after a virtual position is successfully opened.
- Position lifecycle Telegram alerts for opened and closed virtual positions.
- Environment-controlled live startup through `LIVE_RUNNER_ENABLED=true`.
- Configurable loop interval through `LIVE_CYCLE_INTERVAL_SECONDS`.
- Optional finite-run support through `LIVE_RUNNER_MAX_CYCLES` for smoke tests.
- Safe default: live mode is disabled unless explicitly enabled by environment.

## Intentional exclusions

- No Binance private account access.
- No API key usage.
- No real order placement, modification, cancellation, or execution.
- No WebSocket loop.
- No persistent virtual-position storage.
- No Docker, systemd, or VPS deployment files.
- No automatic calibration parameter application.
- No old direct-threshold strategy logic copied from the previous project.

## Operational notes

For a VPS run after later deployment work, the expected environment is:

```bash
CONFIG_PATH=config.yaml
TELEGRAM_BOT_TOKEN=<real token outside git>
TELEGRAM_CHAT_ID=<real chat id outside git>
LIVE_RUNNER_ENABLED=true
LIVE_CYCLE_INTERVAL_SECONDS=900
LIVE_RUNNER_MAX_CYCLES=
```

Real Telegram credentials must stay in environment variables, not in git.
