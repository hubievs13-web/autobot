"""Telegram /start command polling.

This module replies to inbound Telegram /start commands only. It does not place, modify,
or close exchange orders.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from crypto_flow_bot_v2.config import BotConfig
from crypto_flow_bot_v2.logging import get_logger
from crypto_flow_bot_v2.start_message import format_start_message
from crypto_flow_bot_v2.telegram import (
    TelegramAlertError,
    TelegramTransport,
    UrlLibTelegramTransport,
)

LOGGER = get_logger(__name__)
START_COMMAND = "/start"
USER_AGENT = "crypto-flow-bot-v2/0.1.0"


@dataclass(frozen=True, slots=True)
class TelegramCommandUpdate:
    """Minimal inbound Telegram update needed to handle or acknowledge /start."""

    update_id: int
    chat_id: str | None = None
    text: str | None = None


class TelegramStartCommandPoller:
    """Poll Telegram updates and reply to /start commands with a Russian welcome message."""

    def __init__(
        self,
        config: BotConfig,
        transport: TelegramTransport | None = None,
        poll_interval_seconds: float = 3.0,
    ) -> None:
        self._config = config
        self._transport = transport or UrlLibTelegramTransport.from_config(config.telegram)
        self._poll_interval_seconds = poll_interval_seconds
        self._update_offset: int | None = None
        self._processed_update_ids: set[int] = set()

    def run_forever(self, stop_event: Event) -> None:
        """Poll until stop_event is set."""

        while not stop_event.is_set():
            try:
                handled = self.run_once()
            except Exception:
                LOGGER.exception("failed to process Telegram /start updates")
            else:
                if handled:
                    LOGGER.info("Telegram /start commands handled: %s", handled)
            stop_event.wait(self._poll_interval_seconds)

    def run_once(self) -> int:
        """Poll Telegram once and return the number of /start replies sent."""

        telegram = self._config.telegram
        if not telegram.enabled:
            return 0

        bot_token = os.getenv(telegram.bot_token_env, "").strip()
        if not bot_token:
            return 0

        updates = self._get_updates(bot_token)

        handled = 0
        for update in updates:
            if update.update_id in self._processed_update_ids:
                continue
            if not _is_start_command(update.text) or not update.chat_id:
                self._mark_update_processed(update.update_id)
                continue
            try:
                send_result = self._transport.send_message(
                    bot_token=bot_token,
                    chat_id=update.chat_id,
                    text=format_start_message(),
                    parse_mode=telegram.parse_mode,
                )
                if not send_result.ok:
                    msg = (
                        "Telegram API returned unsuccessful send result "
                        "for /start welcome message."
                    )
                    raise TelegramAlertError(msg)
            except Exception:
                LOGGER.exception(
                    "failed to send Telegram /start welcome message update_id=%s chat_id=%s",
                    update.update_id,
                    update.chat_id,
                )
                continue
            self._mark_update_processed(update.update_id)
            handled += 1

        self._advance_update_offset(updates)
        return handled

    def _get_updates(self, bot_token: str) -> tuple[TelegramCommandUpdate, ...]:
        payload = {"timeout": "0"}
        if self._update_offset is not None:
            payload["offset"] = str(self._update_offset)
        base_url = self._config.telegram.base_url.rstrip("/")
        url = f"{base_url}/bot{bot_token}/getUpdates?{urlencode(payload)}"
        request = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")

        try:
            with urlopen(request, timeout=self._config.telegram.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw_body = response.read().decode(charset)
        except HTTPError as exc:
            msg = f"Telegram HTTP error {exc.code} while fetching updates."
            raise TelegramAlertError(msg) from exc
        except URLError as exc:
            msg = f"Telegram request failed while fetching updates: {exc.reason}"
            raise TelegramAlertError(msg) from exc
        except TimeoutError as exc:
            msg = "Telegram request timed out while fetching updates."
            raise TelegramAlertError(msg) from exc

        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            msg = "Telegram returned invalid JSON."
            raise TelegramAlertError(msg) from exc
        if not isinstance(decoded, dict) or not decoded.get("ok", False):
            msg = "Telegram API rejected getUpdates request."
            raise TelegramAlertError(msg)

        raw_updates = decoded.get("result", [])
        if not isinstance(raw_updates, list):
            msg = "Telegram returned unsupported updates payload."
            raise TelegramAlertError(msg)
        return tuple(
            update
            for raw_update in raw_updates
            if (update := _parse_update(raw_update)) is not None
        )

    def _mark_update_processed(self, update_id: int) -> None:
        self._processed_update_ids.add(update_id)

    def _advance_update_offset(self, updates: tuple[TelegramCommandUpdate, ...]) -> None:
        next_offset = self._update_offset
        for update_id in sorted(update.update_id for update in updates):
            if next_offset is not None and update_id < next_offset:
                self._processed_update_ids.discard(update_id)
                continue
            if update_id not in self._processed_update_ids:
                break
            next_offset = update_id + 1
            self._processed_update_ids.discard(update_id)

        self._update_offset = next_offset
        if next_offset is not None:
            self._processed_update_ids = {
                update_id for update_id in self._processed_update_ids if update_id >= next_offset
            }


def _is_start_command(text: str | None) -> bool:
    if text is None:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    command = stripped.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
    return command == START_COMMAND


def _parse_update(raw_update: object) -> TelegramCommandUpdate | None:
    if not isinstance(raw_update, dict):
        return None
    update_id = raw_update.get("update_id")
    if not isinstance(update_id, int):
        return None

    message = raw_update.get("message")
    if not isinstance(message, dict):
        return TelegramCommandUpdate(update_id=update_id)
    text = message.get("text")
    chat = message.get("chat")
    chat_id: str | None = None
    if isinstance(chat, dict):
        raw_chat_id = chat.get("id")
        if isinstance(raw_chat_id, int | str):
            chat_id = str(raw_chat_id)
    return TelegramCommandUpdate(
        update_id=update_id,
        chat_id=chat_id,
        text=text if isinstance(text, str) else None,
    )
