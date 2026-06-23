"""Paleta y estilos Plotly del dashboard SIRA."""

# Colores de marca (logo_sira_3.png)
C_NAVY = "#0a1628"
C_NAVY_MID = "#0f2847"
C_BORDER = "#1e4976"
C_CYAN = "#22d3ee"
C_TEAL = "#06b6d4"
C_ORANGE = "#f97316"
C_GREEN = "#22c55e"
C_TEXT = "#f0f9ff"
C_MUTED = "#94a3b8"

COLORES = {
    "MÍNIMO": "#2ECC71",
    "BAJO": "#F1C40F",
    "MODERADO": "#E67E22",
    "ALTO": "#E74C3C",
    "CRÍTICO": "#8B0000",
}

PLOTLY_BG = dict(
    paper_bgcolor=C_NAVY_MID,
    plot_bgcolor=C_NAVY_MID,
    font=dict(color=C_TEXT),
)
