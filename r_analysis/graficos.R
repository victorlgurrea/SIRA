# Gráficos desde dashboard_data.json
library(jsonlite)
library(dplyr)
library(ggplot2)
source("config.R")

COLORES <- c("MÍNIMO" = "#2ECC71", "BAJO" = "#F1C40F", "MODERADO" = "#E67E22",
             "ALTO" = "#E74C3C", "CRÍTICO" = "#8B0000")

generar_graficos <- function() {
  if (!file.exists(DATA_FILE)) stop("Ejecuta primero: python ingesta.py")
  raw <- fromJSON(DATA_FILE, simplifyDataFrame = FALSE)
  sismos <- bind_rows(lapply(raw$sismos, as.data.frame))
  oce <- bind_rows(lapply(raw$oceanografia$serie_horaria, as.data.frame))
  dir.create(OUTPUT_DIR, recursive = TRUE, showWarnings = FALSE)

  if (nrow(sismos)) {
    sismos$nivel_alerta <- factor(sismos$nivel_alerta, levels = names(COLORES), ordered = TRUE)
    ggsave(file.path(OUTPUT_DIR, "01_magnitud.png"),
           ggplot(sismos, aes(magnitud, fill = nivel_alerta)) + geom_histogram(binwidth = 0.2) +
             scale_fill_manual(values = COLORES) + theme_minimal(), width = 10, height = 5, dpi = 150)
    ggsave(file.path(OUTPUT_DIR, "02_mapa.png"),
           ggplot(sismos, aes(lon, lat, size = magnitud, color = nivel_alerta)) + geom_point(alpha = 0.7) +
             annotate("point", ZONA$lon_ref, ZONA$lat_ref, color = "navy", size = 4, shape = 18) +
             scale_color_manual(values = COLORES) + coord_fixed(1.3) + theme_minimal(), width = 10, height = 7, dpi = 150)
  }
  if (nrow(oce)) {
    oce$timestamp <- as.POSIXct(oce$timestamp, tz = "UTC")
    ggsave(file.path(OUTPUT_DIR, "03_sst.png"),
           ggplot(oce, aes(timestamp, sst_c)) + geom_line(color = "#2471A3") + theme_minimal(), width = 10, height = 5, dpi = 150)
    ggsave(file.path(OUTPUT_DIR, "04_corrientes.png"),
           ggplot(oce, aes(timestamp, corriente_vel_ms)) + geom_line(color = "#16A085") + theme_minimal(), width = 10, height = 5, dpi = 150)
  }
  cat("Gráficos en:", OUTPUT_DIR, "\n")
}

if (!interactive()) generar_graficos()
