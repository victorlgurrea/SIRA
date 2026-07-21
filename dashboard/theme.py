"""Paleta y estilos Plotly del dashboard SIRA."""

# Colores de marca (logo-sira_4.png)
C_NAVY = "#0a1628"
C_NAVY_MID = "#0f2847"
C_BORDER = "#1e4976"
C_CYAN = "#22d3ee"
C_TEAL = "#06b6d4"
C_ORANGE = "#f97316"
C_GREEN = "#22c55e"
C_TEXT = "#f0f9ff"
C_MUTED = "#94a3b8"

C_NAVY_LIGHT = "#f8fafc"
C_TEXT_LIGHT = "#0f172a"
C_MUTED_LIGHT = "#64748b"

COLORES = {
    "MÍNIMO": "#2ECC71",
    "BAJO": "#F1C40F",
    "MODERADO": "#E67E22",
    "ALTO": "#E74C3C",
    "MUY ALTO": "#ef4444",
    "CRÍTICO": "#8B0000",
}

PLOTLY_BG = dict(
    paper_bgcolor=C_NAVY_MID,
    plot_bgcolor=C_NAVY_MID,
    font=dict(color=C_TEXT),
)

PLOTLY_BG_LIGHT = dict(
    paper_bgcolor=C_NAVY_LIGHT,
    plot_bgcolor=C_NAVY_LIGHT,
    font=dict(color=C_TEXT_LIGHT),
)


def plotly_bg(theme: str = "dark") -> dict:
    return PLOTLY_BG_LIGHT if theme == "light" else PLOTLY_BG


def chart_text(theme: str = "dark") -> str:
    return C_TEXT_LIGHT if theme == "light" else C_TEXT


def chart_muted(theme: str = "dark") -> str:
    return C_MUTED_LIGHT if theme == "light" else C_MUTED

