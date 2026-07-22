Scripts de investigación y sondeo de APIs externas (SAIH, Ebro, CHE, etc.).
No forman parte del runtime de ingesta ni del dashboard.

Bootstrap (imports sira.*)
──────────────────────────
Los probes necesitan el paquete python/sira/ en el path. Opciones:

  1. Desde la raíz del repo, con helper:
       py -c "import sys; sys.path[:0]=['scripts','python']; from _bootstrap import ensure_python_path; ensure_python_path(); ..."

  2. Al inicio de cada script (patrón recomendado):

       import sys
       from pathlib import Path
       ROOT = Path(__file__).resolve().parents[2]   # repo root (desde scripts/research/)
       sys.path.insert(0, str(ROOT / "python"))
       sys.path.insert(0, str(ROOT / "scripts"))
       from _bootstrap import ensure_python_path
       ensure_python_path()

       from sira.infrastructure.http.client import fetch_text

  3. Scripts en scripts/ (no research/): parents[1] apunta al repo root.

Imports
───────
  sira.infrastructure.http.client     fetch_text, fetch_json, read_dashboard
  sira.config.settings                ALLOWED_HOSTS, API_KEY, etc.
  sira.infrastructure.sources.*       conectores (hidrología, meteo, …)

Build de datos geo
──────────────────
  py scripts/build/build_geo_es.py
  Ver scripts/build/README.txt
