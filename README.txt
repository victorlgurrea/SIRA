SIRA — Sistema Ibérico de Riesgos y Alerta
═══════════════════════════════════════════

Monitorización peninsular: sismos (Mediterráneo, Cantábrico, Atlántico),
oceanografía costera y previsión meteorológica (AEMET / Open-Meteo).

  .env              configuración
  startup.bat       arranque automático
  python/
    config.py       carga .env
    core.py         HTTP seguro + JSON
    ingesta.py      descarga datos
    api_server.py   API local
    scheduler.py    ingesta periódica
    notificaciones.py
  dashboard/app.py  interfaz web
  r_analysis/       gráficos R

Uso
───
  startup.bat
  py startup.py
  cd python && py ingesta.py

Seguridad
─────────
  API_KEY en .env       protege POST /api/actualizar
  API_HOST=127.0.0.1    solo red local por defecto
  .env en .gitignore    no subir credenciales
