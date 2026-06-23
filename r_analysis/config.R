# Lee .env y expone ZONA para R
ROOT <- if (file.exists(".env")) normalizePath(".") else normalizePath("..")

read_env <- function(path = file.path(ROOT, ".env")) {
  out <- list()
  if (!file.exists(path)) return(out)
  for (line in readLines(path, warn = FALSE, encoding = "UTF-8")) {
    line <- trimws(line)
    if (!nchar(line) || startsWith(line, "#")) next
    kv <- strsplit(line, "=", fixed = TRUE)[[1]]
    if (length(kv) >= 2) out[[kv[1]]] <- paste(kv[-1], collapse = "=")
  }
  out
}

ENV <- read_env()
get <- function(k, default) if (!is.null(ENV[[k]])) ENV[[k]] else default
num <- function(k, default) as.numeric(get(k, default))

ZONA <- list(
  nombre = get("ZONA_NOMBRE", "Mediterráneo Occidental - Costa Valenciana"),
  lat_min = num("MAPA_LAT_MIN", 32), lat_max = num("MAPA_LAT_MAX", 46),
  lon_min = num("MAPA_LON_MIN", -12), lon_max = num("MAPA_LON_MAX", 8),
  lat_ref = num("LAT_REF", 39.47), lon_ref = num("LON_REF", -0.38),
  ciudad_ref = get("CIUDAD_REF", "Valencia")
)
DATA_FILE <- file.path(ROOT, "data", "processed", "dashboard_data.json")
OUTPUT_DIR <- file.path(ROOT, "data", "processed", "graficos")
