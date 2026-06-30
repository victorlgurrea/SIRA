"""Alertas email/Telegram."""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from config import (
    ALERT_EMAIL,
    HTTP_TIMEOUT,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    ZONA,
)
from core import post_json, read_dashboard
from db import ids_ya_notificados, marcar_notificado

log = logging.getLogger(__name__)


def evaluar_alertas() -> bool:
    data = read_dashboard()
    criticos = [s for s in data.get("sismos", []) if s.get("score_total", 0) >= ZONA["umbral_score_alerta"]]
    ids = sorted({str(s["id"]) for s in criticos if s.get("id")})
    if not ids:
        marcar_notificado([])
        return False
    if ids == ids_ya_notificados():
        return False

    top = max(criticos, key=lambda s: s["score_total"])
    msg = f"[SIRA] {top['nivel_alerta']} — M{top['magnitud']} score {top['score_total']}\n{top['lugar']} ({top['dist_valencia_km']} km de Valencia)"
    log.warning(msg)

    host, user, pwd, to = SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL
    if all((host, user, pwd, to)):
        try:
            mail = MIMEText(msg, "plain", "utf-8")
            mail["Subject"], mail["From"], mail["To"] = "[SIRA] Alerta", user, to
            with smtplib.SMTP(host, SMTP_PORT, timeout=HTTP_TIMEOUT) as srv:
                srv.starttls()
                srv.login(user, pwd)
                srv.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("Email: %s", exc)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            post_json(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                {"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            )
        except (OSError, ValueError) as exc:
            log.warning("Telegram: %s", exc)

    marcar_notificado(ids)
    return True
