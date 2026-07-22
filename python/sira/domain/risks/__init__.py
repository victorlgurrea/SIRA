"""Índices y modelos de riesgo."""

from sira.domain.risks.local import calcular_riesgo_local
from sira.domain.risks.meteo import calcular_riesgo_meteo

__all__ = ["calcular_riesgo_local", "calcular_riesgo_meteo"]
