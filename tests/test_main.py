import logging

from crypto_flow_bot_v2 import main as app_main
from crypto_flow_bot_v2.config import BotConfig, parse_config
from crypto_flow_bot_v2.live_runner import LiveRunStats
from crypto_flow_bot_v2.telegram import TelegramAlertResult, TelegramAlertStatus


def test_live_runner_enabled_defaults_to_true_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_RUNNER_ENABLED", raising=False)

    assert app_main._live_runner_enabled() is True


def test_live_runner_enabled_treats_empty_env_as_default_true(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_RUNNER_ENABLED", "  ")

    assert app_main._live_runner_enabled() is True


def test_live_runner_enabled_accepts_true_values(monkeypatch) -> None:
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("LIVE_RUNNER_ENABLED", value)

        assert app_main._live_runner_enabled() is True


def test_live_runner_enabled_respects_explicit_false_values(monkeypatch) -> None:
    for value in ("0", "false", "FALSE", "no", "off"):
        monkeypatch.setenv("LIVE_RUNNER_ENABLED", value)

        assert app_main._live_runner_enabled() is False


def test_live_runner_enabled_keeps_unknown_values_enabled(monkeypatch, caplog) -> None:
    monkeypatch.setenv("LIVE_RUNNER_ENABLED", "maybe")

    with caplog.at_level(logging.WARNING, logger="crypto_flow_bot_v2.main"):
        assert app_main._live_runner_enabled() is True

    assert "Unrecognized LIVE_RUNNER_ENABLED='maybe'" in caplog.text
    assert "keeping live runner enabled by default" in caplog.text


def test_live_runner_interval_prefers_primary_env(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_RUNNER_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("LIVE_CYCLE_INTERVAL_SECONDS", "900")

    assert app_main._live_runner_interval_seconds() == 60


def test_live_runner_interval_supports_legacy_env(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_RUNNER_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("LIVE_CYCLE_INTERVAL_SECONDS", "120")

    assert app_main._live_runner_interval_seconds() == 120


def test_main_sends_startup_message_once_when_live_runner_enabled(monkeypatch) -> None:
    config = _config(enabled=True)
    startup_messages: list[str] = []
    stopped: list[tuple[object, object]] = []

    class FakeNotifier:
        def __init__(self, config: BotConfig) -> None:
            self.config = config

        def _send(self, text: str) -> TelegramAlertResult:
            startup_messages.append(text)
            return TelegramAlertResult(status=TelegramAlertStatus.SENT, message="sent")

    class FakeRunner:
        from_config_calls: list[tuple[BotConfig, int, str | None]] = []
        run_calls: list[int | None] = []

        @classmethod
        def from_config(
            cls,
            config: BotConfig,
            cycle_interval_seconds: int = 900,
            position_state_path: str | None = None,
        ) -> "FakeRunner":
            cls.from_config_calls.append((config, cycle_interval_seconds, position_state_path))
            return cls()

        def run(self, max_cycles: int | None = None) -> LiveRunStats:
            self.run_calls.append(max_cycles)
            return LiveRunStats(
                cycles=1,
                snapshots_built=0,
                build_errors=0,
                decisions_evaluated=0,
                positions_opened=0,
                positions_closed=0,
                telegram_alerts_sent=0,
                telegram_alerts_skipped=0,
                telegram_alert_errors=0,
            )

    monkeypatch.setenv("LIVE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("LIVE_RUNNER_MAX_CYCLES", "1")
    monkeypatch.setenv("BOT_ENV", "dummy")
    monkeypatch.setenv("CHAT_ENV", "dummy-chat")
    monkeypatch.delenv("LIVE_RUNNER_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("LIVE_CYCLE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("POSITION_STATE_PATH", raising=False)
    monkeypatch.setattr(app_main, "load_config", lambda path: config)
    monkeypatch.setattr(app_main, "configure_logging", lambda logging_config: None)
    monkeypatch.setattr(app_main, "TelegramAlertService", FakeNotifier)
    monkeypatch.setattr(app_main, "LiveAlertRunner", FakeRunner)
    monkeypatch.setattr(app_main, "_start_telegram_start_poller", lambda cfg: (object(), object()))
    monkeypatch.setattr(app_main, "_stop_telegram_start_poller", stopped.append)

    exit_code = app_main.main()

    assert exit_code == 0
    assert startup_messages == [app_main.LIVE_RUNNER_STARTUP_MESSAGE]
    assert FakeRunner.from_config_calls == [(config, 900, None)]
    assert FakeRunner.run_calls == [1]
    assert len(stopped) == 1


def test_startup_diagnostics_logs_missing_telegram_credentials(monkeypatch, caplog) -> None:
    config = _config(enabled=True)
    monkeypatch.delenv("BOT_ENV", raising=False)
    monkeypatch.delenv("CHAT_ENV", raising=False)

    with caplog.at_level(logging.INFO, logger="crypto_flow_bot_v2.main"):
        app_main._log_startup_diagnostics(config=config, live_runner_enabled=True)

    assert "LIVE_RUNNER_ENABLED=True" in caplog.text
    assert "telegram.enabled=True" in caplog.text
    assert "token present: no" in caplog.text
    assert "chat_id present: no" in caplog.text
    assert "messages will not be sent because credentials are missing" in caplog.text


def _config(enabled: bool) -> BotConfig:
    return parse_config(
        {
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "timeframes": {"entry": "15m", "context": "1h", "macro": "4h"},
            "binance": {
                "base_url": "https://fapi.binance.com",
                "timeout_seconds": 10.0,
                "kline_limit": 300,
                "derivatives_data_limit": 100,
            },
            "telegram": {
                "enabled": enabled,
                "bot_" "token_env": "BOT_ENV",
                "chat_" "id_env": "CHAT_ENV",
                "base_url": "https://api.telegram.org",
                "timeout_seconds": 10.0,
                "parse_mode": "HTML",
            },
            "logging": {"level": "INFO", "jsonl_path": "logs/events.jsonl"},
            "risk": {
                "min_risk_reward": 1.5,
                "atr_stop_multiplier": 1.5,
                "atr_tp_multipliers": [1.5, 2.5, 4.0],
                "trailing_atr_multiplier": 1.0,
                "max_position_minutes": 240,
                "cooldown_minutes": 60,
            },
            "rfa_engine": {
                "min_signal_confidence": 70,
                "watch_confidence": 60,
                "strong_signal_confidence": 85,
                "require_context_alignment": True,
                "require_macro_alignment": True,
            },
        }
    )
