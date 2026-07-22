Generadores de datos geográficos (INE, IGN, AEMET Meteoalerta).

Ejecutar desde la raíz del repo o vía shims en python/:
  cd python && py build_geo_es.py
  cd python && py build_geo_provincias.py
  cd python && py build_geo_ccaa.py
  cd python && py build_geo_aemet_zonas.py

Salida: data/geo/*.json
