"""Alertas email/Telegram."""
from __future__ import annotations

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText

from config import ALERTAS_STATE_FILE, HTTP_TIMEOUT, ZONA
from core import post_json, read_dashboard, read_json_file

log = logging.getLogger(__name__)


def evaluar_alertas() -> bool:
    data = read_dashboard()
    criticos = [s for s in data.get("sismos", []) if s.get("score_total", 0) >= ZONA["umbral_score_alerta"]]
    ids = sorted({str(s["id"]) for s in criticos if s.get("id")})
    if not ids:
        ALERTAS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERTAS_STATE_FILE.write_text('{"ids_alertados":[]}', encoding="utf-8")
        return False
    if ids == read_json_file(ALERTAS_STATE_FILE).get("ids_alertados", []):
        return False

    top = max(criticos, key=lambda s: s["score_total"])
    msg = f"[SIRA] {top['nivel_alerta']} — M{top['magnitud']} score {top['score_total']}\n{top['lugar']} ({top['dist_valencia_km']} km de Valencia)"
    log.warning(msg)

    host, user, pwd, to = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("ALERT_EMAIL")
    if all((host, user, pwd, to)):
        try:
            mail = MIMEText(msg, "plain", "utf-8")
            mail["Subject"], mail["From"], mail["To"] = "[SIRA] Alerta", user, to
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=HTTP_TIMEOUT) as srv:
                srv.starttls()
                srv.login(user, pwd)
                srv.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("Email: %s", exc)

    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            post_json(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": msg})
        except (OSError, ValueError) as exc:
            log.warning("Telegram: %s", exc)

    ALERTAS_STATE_FILE.write_text(json.dumps({"ids_alertados": ids}), encoding="utf-8")
    return True
