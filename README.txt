SIRA — Sistema Ibérico de Riesgos y Alerta
═══════════════════════════════════════════

Monitorización peninsular: sismos, oceanografía costera, meteo (AEMET / Open-Meteo)
y alertas push por municipio.

Estructura
──────────
  .env / .env.example     configuración local
  startup.py / startup.bat arranque API + dashboard
  python/                 API, ingesta, push, meteo, geo
  dashboard/              interfaz Dash (app.py, assets/)
  data/geo/espana.json    catálogo INE (provincia/municipio/localidad)
  data/processed/         JSON generados en runtime (ignorados por git)
  r_analysis/             gráficos R opcionales (no usa el dashboard)
  render.yaml             despliegue Render (sira-api + sira-dashboard)

  App Android: ../WWW/SIRA_MOVILE/android (WebView del dashboard)

Uso local
─────────
  py startup.py
  cd python && py ingesta.py     # actualización manual de datos

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
  Secrets: SIRA_API_URL (servicio API, no el dashboard), SIRA_CRON_SECRET

Web Push
────────
  Activar en el dashboard → notificaciones por municipio (sismos + meteo AEMET).
  Prueba admin: POST /api/push/test (header X-API-Key o X-Cron-Secret).
  Variables: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY (PEM), VAPID_SUBJECT.
