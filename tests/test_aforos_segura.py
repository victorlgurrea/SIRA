"""Tests del parser SAIH Segura (sadder1.php)."""
from __future__ import annotations

from sira.infrastructure.sources.hydrology.segura import parse_sadder_csv, _punto_codigo, _variable_sufijo


SAMPLE_HTML = '''
<input type="hidden" id="csv" value="Relación de Variables: ;03A02 AFORO EN RÍO SEGURA EN BAYO***VARIABLE;DESCRIPCIÓN;FECHA;VALOR;UDS.;***    Q02;Caudal Río Segura Puente del Bayo;21-07-2026 12:55;31.361; ;m³/s***    U01;Nivel Río Segura Bayo;21-07-2026 12:55;1.38; ;m" />
'''


def test_parse_sadder_csv_extrae_caudal_y_nivel():
    vals = parse_sadder_csv(SAMPLE_HTML)
    assert vals["Q02"]["valor"] == 31.361
    assert vals["U01"]["valor"] == 1.38
    assert "12:55" in vals["Q02"]["fecha"]


def test_punto_y_sufijo_variable():
    assert _punto_codigo("03A02A1") == "03A02"
    assert _variable_sufijo("03A02Q02", "03A02") == "Q02"
