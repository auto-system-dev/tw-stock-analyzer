"""Telegram Bot 通知。"""

from __future__ import annotations

import os

import requests


class TelegramConfigError(ValueError):
    """Telegram 環境變數未設定。"""


def get_telegram_config() -> tuple[str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise TelegramConfigError("請設定環境變數 TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise TelegramConfigError("請設定環境變數 TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram_message(
    text: str,
    *,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
) -> dict:
    """透過 Telegram Bot API 發送訊息。"""
    token, chat_id = get_telegram_config()
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or not data.get("ok"):
        description = data.get("description", resp.text)
        raise RuntimeError(f"Telegram 發送失敗：{description}")
    return data
