"""Persistencia SQLite: push, alertas email/Telegram e historial municipal."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sira.config.settings import DB_PATH

log = logging.getLogger(__name__)
_lock = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY NOT NULL,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_notified (
    tipo TEXT NOT NULL,
    alert_id TEXT NOT NULL,
    PRIMARY KEY (tipo, alert_id)
);
CREATE TABLE IF NOT EXISTS push_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas_notificados (
    sismo_id TEXT PRIMARY KEY NOT NULL
);
CREATE TABLE IF NOT EXISTS historial_municipio (
    fecha TEXT NOT NULL,
    municipio_id TEXT NOT NULL,
    score_sismo_max INTEGER NOT NULL DEFAULT 0,
    indice_riesgo_meteo INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (fecha, municipio_id)
);
"""


def _db_path() -> Path:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _conn():
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _lock:
        with _conn() as conn:
            conn.executescript(_SCHEMA)
            _migrate_historial(conn)


def _migrate_historial(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(historial_municipio)")}
    if "indice_impacto_local" not in cols:
        conn.execute(
            "ALTER TABLE historial_municipio ADD COLUMN indice_impacto_local INTEGER NOT NULL DEFAULT 0"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Push subscriptions ---


def list_subscriptions() -> list[dict]:
    init_db()
    with _lock:
        with _conn() as conn:
            rows = conn.execute("SELECT payload FROM push_subscriptions ORDER BY updated_at").fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            data = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("endpoint"):
            out.append(data)
    return out


def save_subscriptions(subs: list[dict]) -> None:
    init_db()
    now = _now_iso()
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM push_subscriptions")
            for sub in subs:
                endpoint = sub.get("endpoint")
                if not endpoint:
                    continue
                conn.execute(
                    "INSERT INTO push_subscriptions (endpoint, payload, updated_at) VALUES (?, ?, ?)",
                    (endpoint, json.dumps(sub, ensure_ascii=False), now),
                )


def add_subscription(sub: dict) -> int:
    init_db()
    endpoint = sub.get("endpoint")
    if not endpoint:
        return len(list_subscriptions())
    subs = list_subscriptions()
    for i, current in enumerate(subs):
        if current.get("endpoint") == endpoint:
            subs[i] = sub
            save_subscriptions(subs)
            return len(subs)
    subs.append(sub)
    save_subscriptions(subs)
    return len(subs)


def remove_subscription(endpoint: str) -> int:
    init_db()
    subs = [s for s in list_subscriptions() if s.get("endpoint") != endpoint]
    save_subscriptions(subs)
    return len(subs)


def count_subscriptions() -> int:
    init_db()
    with _lock:
        with _conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM push_subscriptions").fetchone()
    return int(row["n"]) if row else 0


# --- Push notified state ---


def get_push_state() -> dict:
    init_db()
    tipos = ("sismo", "meteo", "incendio", "tsunami")
    state = {f"ids_{t}": [] for t in tipos}
    with _lock:
        with _conn() as conn:
            for tipo in tipos:
                rows = conn.execute(
                    "SELECT alert_id FROM push_notified WHERE tipo = ? ORDER BY alert_id",
                    (tipo,),
                ).fetchall()
                state[f"ids_{tipo}"] = [str(r["alert_id"]) for r in rows]
            meta = conn.execute("SELECT value FROM push_meta WHERE key = 'updated'").fetchone()
    if meta:
        state["updated"] = meta["value"]
    return state


def save_push_state(state: dict) -> None:
    init_db()
    with _lock:
        with _conn() as conn:
            for tipo in ("sismo", "meteo", "incendio", "tsunami"):
                conn.execute("DELETE FROM push_notified WHERE tipo = ?", (tipo,))
                for aid in state.get(f"ids_{tipo}", []):
                    if aid:
                        conn.execute(
                            "INSERT OR IGNORE INTO push_notified (tipo, alert_id) VALUES (?, ?)",
                            (tipo, str(aid)),
                        )
            conn.execute(
                "INSERT OR REPLACE INTO push_meta (key, value) VALUES (?, ?)",
                ("updated", state.get("updated") or _now_iso()),
            )


# --- Alertas email/Telegram ---


def ids_ya_notificados() -> list[str]:
    init_db()
    with _lock:
        with _conn() as conn:
            rows = conn.execute("SELECT sismo_id FROM alertas_notificados ORDER BY sismo_id").fetchall()
    return [str(r["sismo_id"]) for r in rows]


def marcar_notificado(ids: list[str]) -> None:
    init_db()
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM alertas_notificados")
            for sid in sorted({str(x) for x in ids if x}):
                conn.execute(
                    "INSERT OR IGNORE INTO alertas_notificados (sismo_id) VALUES (?)",
                    (sid,),
                )


# --- Historial municipal ---


def historial_existe(fecha: str, municipio_id: str) -> bool:
    init_db()
    mid = str(municipio_id).zfill(5)
    with _lock:
        with _conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM historial_municipio WHERE fecha = ? AND municipio_id = ?",
                (fecha, mid),
            ).fetchone()
    return row is not None


def insert_historial_municipio(
    fecha: str,
    municipio_id: str,
    *,
    score_sismo_max: int,
    indice_riesgo_meteo: int,
    indice_impacto_local: int = 0,
) -> None:
    init_db()
    mid = str(municipio_id).zfill(5)
    with _lock:
        with _conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO historial_municipio
                (fecha, municipio_id, score_sismo_max, indice_riesgo_meteo, indice_impacto_local)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fecha, mid, int(score_sismo_max), int(indice_riesgo_meteo), int(indice_impacto_local)),
            )


def get_historial_municipio(municipio_id: str, dias: int = 30) -> list[dict]:
    init_db()
    mid = str(municipio_id).zfill(5)
    dias = max(1, min(int(dias), 365))
    with _lock:
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT fecha, municipio_id, score_sismo_max, indice_riesgo_meteo, indice_impacto_local
                FROM historial_municipio
                WHERE municipio_id = ?
                ORDER BY fecha DESC
                LIMIT ?
                """,
                (mid, dias),
            ).fetchall()
    return [
        {
            "fecha": r["fecha"],
            "municipio_id": r["municipio_id"],
            "score_sismo_max": r["score_sismo_max"],
            "indice_riesgo_meteo": r["indice_riesgo_meteo"],
            "indice_impacto_local": r["indice_impacto_local"],
        }
        for r in reversed(rows)
    ]


# --- Migración JSON → SQLite ---


def migrar_desde_json(
    *,
    push_subscriptions_path: Path | None = None,
    push_state_path: Path | None = None,
    alertas_state_path: Path | None = None,
) -> dict:
    """Importa ficheros JSON legacy si existen."""
    from sira.config.settings import ALERTAS_STATE_FILE, PUSH_STATE_FILE, PUSH_SUBSCRIPTIONS_FILE
    from sira.infrastructure.http.client import read_json_file

    init_db()
    stats = {"subscriptions": 0, "push_state": False, "alertas": 0}

    psub = push_subscriptions_path or PUSH_SUBSCRIPTIONS_FILE
    if psub.is_file():
        raw = read_json_file(psub)
        subs = [s for s in raw.get("subscriptions", []) if isinstance(s, dict) and s.get("endpoint")]
        if subs and not list_subscriptions():
            save_subscriptions(subs)
            stats["subscriptions"] = len(subs)
            log.info("Migradas %d suscripciones push desde %s", len(subs), psub)

    pstate = push_state_path or PUSH_STATE_FILE
    if pstate.is_file():
        raw = read_json_file(pstate)
        with _lock:
            with _conn() as conn:
                n = conn.execute("SELECT COUNT(*) AS c FROM push_notified").fetchone()["c"]
        if raw and n == 0:
            state = {
                "ids_sismo": [str(x) for x in raw.get("ids_sismo", raw.get("ids_push", []))],
                "ids_meteo": [str(x) for x in raw.get("ids_meteo", [])],
                "ids_incendio": [str(x) for x in raw.get("ids_incendio", [])],
                "ids_tsunami": [str(x) for x in raw.get("ids_tsunami", [])],
                "updated": raw.get("updated"),
            }
            save_push_state(state)
            stats["push_state"] = True
            log.info("Migrado push_estado desde %s", pstate)

    alertas = alertas_state_path or ALERTAS_STATE_FILE
    if alertas.is_file():
        raw = read_json_file(alertas)
        ids = [str(x) for x in raw.get("ids_alertados", []) if x]
        if ids and not ids_ya_notificados():
            marcar_notificado(ids)
            stats["alertas"] = len(ids)
            log.info("Migradas %d alertas email desde %s", len(ids), alertas)

    return stats


init_db()
