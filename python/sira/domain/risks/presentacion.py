"""Presentación pura de avisos AEMET (sin I/O)."""
from __future__ import annotations

PHENO_ICON = {
    "AT": "🌡️",
    "BT": "🥶",
    "VI": "💨",
    "TO": "⛈️",
    "PR": "🌧️",
    "CO": "🌊",
    "NE": "❄️",
    "VS": "🌫️",
    "NI": "🌁",
    "DH": "💧",
    "GA": "🌬️",
    "RI": "🌊",
    "AL": "🏔️",
}


def fmt_alerta_detalle(alerta: dict) -> str:
    parametro = (alerta.get("parametro") or "").strip()
    if parametro and ";" in parametro:
        parts = [p.strip() for p in parametro.split(";") if p.strip()]
        if len(parts) >= 3:
            return f"{parts[1]}: {parts[2]}"
        if len(parts) == 2:
            return f"{parts[0]}: {parts[1]}"
        if parts:
            return parts[0]
    if parametro:
        return parametro
    return (alerta.get("description") or "Sin detalle").strip()


def icono_alerta(alerta: dict) -> str:
    """Icono del fenómeno; ignora marcadores inválidos (p. ej. 'x')."""
    fen = str(alerta.get("fenomeno") or "").upper().strip()
    if fen in PHENO_ICON:
        return PHENO_ICON[fen]
    icon = str(alerta.get("icon") or "").strip()
    if icon and icon.lower() not in {"x", "-", "—"}:
        return icon
    return "⚠️"
