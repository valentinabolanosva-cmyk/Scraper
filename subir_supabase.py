"""
Sube los CSVs del pipeline a Supabase.
- posts_summary.csv          → tabla `posts`
- comments_analizados.csv    → tabla `comments`

Requiere SUPABASE_URL y SUPABASE_KEY válidos en .env.
Si faltan o siguen con placeholders, sale con código 1 (error)
para que run_pipeline.bat detecte el fallo.
"""

import os
import sys
import math
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

import config

load_dotenv()
URL: str = os.environ.get("SUPABASE_URL", "").strip()
KEY: str = os.environ.get("SUPABASE_KEY", "").strip()

PLACEHOLDERS = {"", "tu-proyecto", "tu-anon-key-de-supabase", "tu-llave-de-openai"}


def _credenciales_validas() -> bool:
    if not URL or not KEY:
        return False
    if any(p and p in URL for p in PLACEHOLDERS if p):
        return False
    if KEY in PLACEHOLDERS:
        return False
    return URL.startswith("https://") and ".supabase.co" in URL


def _posts_summary_path() -> str:
    return os.path.join(config.OUTPUT_DIR, "posts_summary.csv")


def _comments_path() -> str:
    return os.path.join(config.OUTPUT_DIR, "comments_analizados.csv")


def _clean_records(df: pd.DataFrame) -> list:
    """Convierte DataFrame a registros limpios: NaN → None, no strings vacíos en numéricos."""
    df = df.where(pd.notna(df), None)
    records = df.to_dict(orient="records")
    cleaned = []
    for r in records:
        row = {}
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                row[k] = None
            else:
                row[k] = v
        cleaned.append(row)
    return cleaned


def _upsert_en_lotes(supabase: Client, tabla: str, registros: list,
                     on_conflict: str, lote: int = 500) -> int:
    """Upsert en lotes para evitar payloads gigantes. Devuelve filas subidas."""
    total = 0
    for i in range(0, len(registros), lote):
        chunk = registros[i:i + lote]
        supabase.table(tabla).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
        print(f"   [{tabla}] {total}/{len(registros)} subidos...")
    return total


def subir_datos() -> int:
    print("=" * 55)
    print("         INICIANDO SUBIDA A SUPABASE")
    print("=" * 55)

    supabase: Client = create_client(URL, KEY)
    errores = 0

    # 1. VIDEOS (Antes 'posts')
    posts_csv = _posts_summary_path()
    print(f"\n[1] Leyendo {posts_csv}...")
    if os.path.exists(posts_csv):
        df_posts = pd.read_csv(posts_csv, encoding="utf-8-sig")
        # Mapeo de nombres de columnas para que coincidan con tu tabla 'videos'
        df_posts = df_posts.rename(columns={
            'post_url': 'url',
            'post_text': 'titulo',
            'total_likes': 'likes',
            'total_comments': 'comentarios',
            'total_shares': 'compartidos',
            'post_date': 'fecha_publicacion'
        })
        registros = _clean_records(df_posts)
        if registros:
            print(f" -> Subiendo {len(registros)} registros a la tabla 'videos'...")
            try:
                _upsert_en_lotes(supabase, "videos", registros, on_conflict="url")
                print(" -> OK")
            except Exception as e:
                print(f" -> [!] Error subiendo a 'videos': {e}")
                errores += 1

    # 2. COMENTARIOS (Antes 'comments')
    comm_csv = _comments_path()
    print(f"\n[2] Leyendo {comm_csv}...")
    if os.path.exists(comm_csv):
        df_comm = pd.read_csv(comm_csv, encoding="utf-8-sig")
        # Mapeo para tu tabla 'comentarios'
        df_comm = df_comm.rename(columns={
            'post_url': 'video_url',
            'comment_text': 'comentario',
            'commenter_name': 'usuario',
            'comment_likes': 'likes',
            'comment_date': 'fecha',
            'sentimiento': 'sentimiento'
        })
        registros = _clean_records(df_comm)
        if registros:
            print(f" -> Subiendo {len(registros)} registros a la tabla 'comentarios'...")
            try:
                # Usamos video_url y comentario como conflicto para evitar duplicados
                _upsert_en_lotes(supabase, "comentarios", registros, on_conflict="video_url,comentario")
                print(" -> OK")
            except Exception as e:
                print(f" -> [!] Error subiendo a 'comentarios': {e}")
                errores += 1

    print("\n" + "=" * 55)
    if errores == 0:
        print("         ¡ACTUALIZACIÓN EN LA NUBE FINALIZADA!")
    else:
        print(f"         TERMINADO CON {errores} ERROR(ES)")
    print("=" * 55 + "\n")
    return errores


if __name__ == "__main__":
    if not _credenciales_validas():
        print("\n[!] ERROR: Faltan credenciales válidas de Supabase en .env")
        print("    Configura SUPABASE_URL (https://<proyecto>.supabase.co)")
        print("    y SUPABASE_KEY (anon o service_role) antes de ejecutar.")
        print("    Aborta con código de error para detener el pipeline.\n")
        sys.exit(1)

    try:
        errores = subir_datos()
        sys.exit(0 if errores == 0 else 1)
    except Exception as e:
        print(f"\n[!] Falla crítica en subida: {e}")
        sys.exit(1)
