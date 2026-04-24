"""
Analiza los comentarios scrapeados y genera comments_analizados.csv
con columnas: temperatura, tipo_humor, justificacion, sentimiento.
"""

import os
import sys

import pandas as pd

import config
from moderacion_colombia import analizar_comentario_colombia


def procesar_todo() -> int:
    print("Iniciando Calificación de Temperatura Emocional para el Dashboard...")

    entrada = os.path.join(config.OUTPUT_DIR, "comments.csv")
    salida = os.path.join(config.OUTPUT_DIR, "comments_analizados.csv")

    if not os.path.exists(entrada):
        print(f"[!] No se encontró {entrada}")
        return 1

    # utf-8-sig maneja el BOM que escribe storage.py
    df = pd.read_csv(entrada, encoding="utf-8-sig")

    if df.empty:
        print(f"[!] {entrada} está vacío — nada que analizar.")
        df.to_csv(salida, index=False, encoding="utf-8-sig")
        return 0

    resultados = df["comment_text"].fillna("").apply(analizar_comentario_colombia)

    df["temperatura"] = resultados.apply(
        lambda r: round(min(1.0, max(0.0, float(r["temperatura"]))), 2)
    )
    df["tipo_humor"] = resultados.apply(lambda r: r["tipo_humor"])
    df["justificacion"] = resultados.apply(lambda r: r["justificacion"])
    df["sentimiento"] = resultados.apply(lambda r: r["sentimiento_dashboard"])

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"¡{len(df)} comentarios calificados con éxito! -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(procesar_todo())
