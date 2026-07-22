SIRA — Sistema Ibérico de Riesgos y Alerta
═══════════════════════════════════════════

Monitorización peninsular: sismos, oceanografía costera, meteo (AEMET / Open-Meteo)
y alertas push por municipio.

Estructura
──────────
  .env / .env.example     configuración local
  startup.py / startup.bat arranque API + dashboard
  python/                 entry points (api_server, ingesta, scheduler, bootstrap)
  python/sira/            paquete principal
    config/               variables de entorno (.env)
    domain/
      risks/              índices de riesgo (local, meteo)
      seismic/            sismos, tsunami oficial
      costa/              capas costeras en mapa
    infrastructure/
      http/               cliente HTTP seguro y AEMET
      parsers/            parseo USGS, FIRMS, etc.
      persistence/        SQLite (push, historial)
      geo/                catálogo INE, topojson, zonas AEMET
      sources/            hidrología, incendios, meteo
    services/
      ingesta/            orquestación, CLI (runner) y estado de fuentes
      push/               Web Push VAPID
      historial/          snapshots diarios por municipio
      notifications/      email y Telegram
      overlays/           sismos/avisos de prueba
    api/                  FastAPI REST (/api/dashboard, push, cron)
  dashboard/              interfaz Dash
    geo/                  contexto, selector y panel geográfico
    ui/                   componentes y tema
    charts/               figuras Plotly
    routes/               Flask (/status, PWA, manifest)
  data/geo/espana.json    catálogo INE (provincia/municipio/localidad)
  data/processed/         JSON generados en runtime + SQLite (ignorados por git)
  scripts/build/          generadores de data/geo/*.json
  scripts/research/       probes y utilidades de investigación de APIs
  r_analysis/             gráficos R opcionales (no usa el dashboard)
  render.yaml             despliegue Render (sira-api + sira-dashboard)

  App Android: ../WWW/SIRA_MOVILE/android (WebView del dashboard)

Uso local
─────────
  py startup.py
  cd python && py ingesta.py                    # ingesta manual
  cd python && py -m sira.services.ingesta        # equivalente
  cd python && py scheduler.py --una-vez          # ingesta + alertas (una vez)
  cd python && py -m sira.services.ingesta --scheduler --una-vez
  py scripts/migrar_json_a_sqlite.py            # migración JSON → SQLite (una vez)
  py scripts/build/build_geo_es.py              # regenerar data/geo/espana.json

Seguridad (modo consulta por defecto)
─────────────────────────────────────
  ALLOW_DATA_REFRESH=false   solo lectura en dashboard y API
  API_KEY                    POST /api/actualizar y /api/push/test
  CRON_SECRET                POST /api/cron/ingesta (GitHub Actions)
  .env en .gitignore

Despliegue Render
─────────────────
  1. Blueprint desde GitHub (render.yaml).
  2. Variables en sira-secrets: AEMET_API_KEY, API_KEY, CRON_SECRET, VAPID_*.
  3. Dashboard: https://sira-dashboard.onrender.com
  4. API: URL exacta del servicio sira-api en Render (suele llevar sufijo).

Cron horario (GitHub Actions)
─────────────────────────────
  Workflow: .github/workflows/ingesta-hourly.yml
  Tests CI: .github/workflows/tests.yml (pytest en cada push/PR a main)
  Secrets: SIRA_API_URL (servicio API, no el dashboard), SIRA_CRON_SECRET

Persistencia SQLite (push + historial)
──────────────────────────────────────
  DB_PATH=data/processed/sira.db (configurable en .env)
  Suscripciones Web Push, estado de notificaciones e historial municipal
  viven en SQLite, no en JSON efímero del disco de Render.
  Migración única: py scripts/migrar_json_a_sqlite.py
  En Render (disco efímero):
    1. Añade un volumen persistente (p. ej. montado en /data).
    2. Variable DB_PATH=/data/sira.db en sira-api y sira-dashboard.
    3. Alternativa: Postgres gratuito en Render y adaptar db.py (futuro).
  Sin volumen, cada deploy borra la base local; la migración reimporta JSON
  legacy si aún existen en el primer arranque.

Web Push
────────
  Activar en el dashboard → notificaciones por municipio (sismos + meteo AEMET).
  Prueba admin: POST /api/push/test (header X-API-Key o X-Cron-Secret).
  Variables: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (PEM), VAPID_SUBJECT.
