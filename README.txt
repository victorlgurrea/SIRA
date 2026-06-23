SIRA — Sistema Ibérico de Riesgos y Alerta
═══════════════════════════════════════════

Monitorización peninsular: sismos (Mediterráneo, Cantábrico, Atlántico),
oceanografía costera y previsión meteorológica (AEMET / Open-Meteo).

  .env              configuración
  startup.bat       arranque automático
  python/
    config.py       carga .env y constantes
    core.py         HTTP saliente + JSON
    ingesta.py      descarga datos
    api_server.py   API local (solo consulta por defecto)
    scheduler.py    ingesta periódica (manual)
    notificaciones.py
  dashboard/
    _bootstrap.py   imports compartidos
    app.py          interfaz Dash (layout + gráficos)
    theme.py        paleta de colores
    components.py   tarjetas y bloques UI
    assets/
      sira.css      estilos responsive
      logo_sira_2.png
  r_analysis/       gráficos R (opcional)

Uso
───
  startup.bat
  py startup.py
  cd python && py ingesta.py          # actualización manual
  cd python && py scheduler.py        # ingesta periódica

Seguridad (modo consulta)
─────────────────────────
  ALLOW_DATA_REFRESH=false   solo lectura en dashboard y API (por defecto)
  API_KEY en .env            obligatoria para POST /api/actualizar
  ENABLE_API_DOCS=false      oculta Swagger en producción (por defecto)
  API_HOST=127.0.0.1         solo red local por defecto
  HTTP saliente              whitelist de hosts en config.py
  .env en .gitignore         no subir credenciales

Para habilitar actualización desde el dashboard:
  ALLOW_DATA_REFRESH=true en .env
