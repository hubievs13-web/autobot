import logging

from crypto_flow_bot_v2.config import BotConfig, parse_config
from crypto_flow_bot_v2.telegram import TelegramSendResult
from crypto_flow_bot_v2.telegram_start import TelegramCommandUpdate, TelegramStartCommandPoller


class FakeTelegramTransport:
    def __init__(self, fail_chat_ids: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self.fail_chat_ids = fail_chat_ids or set()

    def send_message(
        self,
        bot_token: str,
        chat_id: str,
        text: str,
        parse_mode: str,
    ) -> TelegramSendResult:
        if chat_id in self.fail_chat_ids:
            raise RuntimeError("send failed")
        self.calls.append((bot_token, chat_id, text, parse_mode))
        return TelegramSendResult(ok=True, message_id=42)


def test_start_poller_replies_to_inbound_start_command(monkeypatch) -> None:
    monkeypatch.setenv("BOT_ENV", "DUMMY")
    transport = FakeTelegramTransport()
    poller = TelegramStartCommandPoller(_config(), transport=transport)
    _set_updates(
        poller,
        (
            TelegramCommandUpdate(update_id=10, chat_id="START_CHAT", text="/start"),
            TelegramCommandUpdate(update_id=11, chat_id="OTHER_CHAT", text="hello"),
        ),
    )

    handled = poller.run_once()

    assert handled == 1
    assert poller._update_offset == 12  # noqa: SLF001
    assert len(transport.calls) == 1
    bot_token, chat_id, text, parse_mode = transport.calls[0]
    assert bot_token == "DUMMY"
    assert chat_id == "START_CHAT"
    assert "Привет" in text
    assert "Реальные сделки не открываю" in text
    assert parse_mode == "HTML"


def test_start_poller_advances_offset_after_successful_start(monkeypatch) -> None:
    monkeypatch.setenv("BOT_ENV", "DUMMY")
    transport = FakeTelegramTransport()
    poller = TelegramStartCommandPoller(_config(), transport=transport)
    _set_updates(
        poller,
        (TelegramCommandUpdate(update_id=10, chat_id="START_CHAT", text="/start"),),
    )

    handled = poller.run_once()

    assert handled == 1
    assert poller._update_offset == 11  # noqa: SLF001
    assert len(transport.calls) == 1
    assert transport.calls[0][1] == "START_CHAT"


def test_start_poller_keeps_offset_when_start_send_fails(monkeypatch, caplog) -> None:
    monkeypatch.setenv("BOT_ENV", "DUMMY")
    transport = FakeTelegramTransport(fail_chat_ids={"START_CHAT"})
    poller = TelegramStartCommandPoller(_config(), transport=transport)
    _set_updates(
        poller,
        (TelegramCommandUpdate(update_id=10, chat_id="START_CHAT", text="/start"),),
    )

    with caplog.at_level(logging.ERROR, logger="crypto_flow_bot_v2.telegram_start"):
        handled = poller.run_once()

    assert handled == 0
    assert poller._update_offset is None  # noqa: SLF001
    assert transport.calls == []
    assert "failed to send Telegram /start welcome message" in caplog.text
    assert "update_id=10" in caplog.text
    assert "chat_id=START_CHAT" in caplog.text


def test_start_poller_skips_invalid_or_non_start_update(monkeypatch) -> None:
    monkeypatch.setenv("BOT_ENV", "DUMMY")
    transport = FakeTelegramTransport()
    poller = TelegramStartCommandPoller(_config(), transport=transport)
    _set_updates(
        poller,
        (TelegramCommandUpdate(update_id=10, chat_id="OTHER_CHAT", text="hello"),),
    )

    handled = poller.run_once()

    assert handled == 0
    assert poller._update_offset == 11  # noqa: SLF001
    assert transport.calls == []


def test_start_poller_preserves_failed_start_in_batch_without_duplicate_replies(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BOT_ENV", "DUMMY")
    transport = FakeTelegramTransport(fail_chat_ids={"FAIL_CHAT"})
    poller = TelegramStartCommandPoller(_config(), transport=transport)
    _set_update_batches(
        poller,
        (
            (
                TelegramCommandUpdate(update_id=10, chat_id="OK_CHAT_1", text="/start"),
                TelegramCommandUpdate(update_id=11, chat_id="FAIL_CHAT", text="/start"),
                TelegramCommandUpdate(update_id=12, chat_id="OTHER_CHAT", text="hello"),
                TelegramCommandUpdate(update_id=13, chat_id="OK_CHAT_2", text="/start"),
            ),
            (
                TelegramCommandUpdate(update_id=11, chat_id="FAIL_CHAT", text="/start"),
                TelegramCommandUpdate(update_id=12, chat_id="OTHER_CHAT", text="hello"),
                TelegramCommandUpdate(update_id=13, chat_id="OK_CHAT_2", text="/start"),
            ),
            (
                TelegramCommandUpdate(update_id=11, chat_id="FAIL_CHAT", text="/start"),
                TelegramCommandUpdate(update_id=12, chat_id="OTHER_CHAT", text="hello"),
                TelegramCommandUpdate(update_id=13, chat_id="OK_CHAT_2", text="/start"),
            ),
        ),
    )

    first_handled = poller.run_once()
    second_handled = poller.run_once()
    transport.fail_chat_ids.clear()
    third_handled = poller.run_once()

    assert first_handled == 2
    assert second_handled == 0
    assert third_handled == 1
    assert poller._update_offset == 14  # noqa: SLF001
    assert [call[1] for call in transport.calls] == ["OK_CHAT_1", "OK_CHAT_2", "FAIL_CHAT"]


def test_start_poller_skips_when_bot_token_missing(monkeypatch) -> None:
    monkeypatch.delenv("BOT_ENV", raising=False)
    transport = FakeTelegramTransport()
    poller = TelegramStartCommandPoller(_config(), transport=transport)

    handled = poller.run_once()

    assert handled == 0
    assert transport.calls == []


def _set_updates(
    poller: TelegramStartCommandPoller,
    updates: tuple[TelegramCommandUpdate, ...],
) -> None:
    def get_updates(bot_token: str) -> tuple[TelegramCommandUpdate, ...]:
        assert bot_token == "DUMMY"
        return updates

    poller._get_updates = get_updates  # noqa: SLF001


def _set_update_batches(
    poller: TelegramStartCommandPoller,
    batches: tuple[tuple[TelegramCommandUpdate, ...], ...],
) -> None:
    batch_iter = iter(batches)

    def get_updates(bot_token: str) -> tuple[TelegramCommandUpdate, ...]:
        assert bot_token == "DUMMY"
        return next(batch_iter)

    poller._get_updates = get_updates  # noqa: SLF001


def _config(enabled: bool = True) -> BotConfig:
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
                "bot_token_env": "BOT_ENV",
                "chat_id_env": "CHAT_ENV",
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
