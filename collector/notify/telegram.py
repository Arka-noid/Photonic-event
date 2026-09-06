"""Invio dei messaggi su Telegram.

Vincolo dell'API: 4096 caratteri per messaggio. Il testo viene quindi spezzato
sui confini di riga, mai a metà di un evento, per non produrre messaggi tagliati
a metà parola.
"""

from __future__ import annotations

import html as html_escape
import time

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 4096
MAX_RETRIES = 3


def esc(text) -> str:
    """Escape per parse_mode=HTML. Telegram rifiuta il messaggio se un '&' o un
    '<' nel titolo di una conferenza non è codificato."""
    return html_escape.escape(str(text or ""), quote=False)


def split_message(text: str, limit: int = LIMIT) -> list[str]:
    """Spezza sui confini di riga; solo un blocco più lungo del limite viene
    troncato per forza."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


class Telegram:
    def __init__(self, token: str, chat_id: str, dry_run: bool = False) -> None:
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        """Invia (o stampa, in dry-run). Ritorna True se tutti i pezzi sono partiti."""
        chunks = split_message(text)
        if self.dry_run:
            for i, chunk in enumerate(chunks, 1):
                print(f"\n--- messaggio Telegram {i}/{len(chunks)} ({len(chunk)} caratteri) ---")
                print(chunk)
            return True
        if not self.configured:
            raise RuntimeError("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID mancanti")

        ok = True
        for chunk in chunks:
            ok = self._send_one(chunk) and ok
        return ok

    def _send_one(self, chunk: str) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(API.format(token=self.token), json=payload, timeout=30)
                if response.status_code == 429:
                    # Telegram dice esattamente quanto aspettare: rispettarlo.
                    wait = response.json().get("parameters", {}).get("retry_after", 5)
                    time.sleep(min(int(wait), 60))
                    continue
                if response.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                if not response.ok:
                    print(f"[telegram] errore {response.status_code}: {response.text[:200]}")
                    return False
                return True
            except requests.RequestException as exc:
                print(f"[telegram] {type(exc).__name__}: {exc}")
                time.sleep(2 ** attempt)
        return False
