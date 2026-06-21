# Deployment guide

Safe startup:

```bash
python -m crypto_flow_bot_v2
```

Live runner startup:

```bash
LIVE_RUNNER_ENABLED=true python -m crypto_flow_bot_v2
```

Docker safe startup:

```bash
docker compose run --rm -e LIVE_RUNNER_ENABLED=false crypto-flow-bot-v2
```
