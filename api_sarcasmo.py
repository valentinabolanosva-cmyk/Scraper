"""
API del analizador de sarcasmo colombiano.
- POST /analizar/         -> clasifica un texto con reglas de moderación.
- POST /update_comment/   -> persiste un cambio manual de sentimiento en el CSV.

Seguridad aplicada:
 * CORS restringido a localhost (servidor del dashboard).
 * Validación de tamaño/tipo de entrada con pydantic.
 * asyncio.Lock para evitar race conditions al escribir el CSV.
 * Rutas absolutas basadas en config.OUTPUT_DIR.
"""

import asyncio
import logging
import os

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client
from dotenv import load_dotenv

import config
from moderacion_colombia import analizar_comentario_colombia

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api_sarcasmo")

# ── Configuración ────────────────────────────────────────────────────────────
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

COMMENTS_CSV = os.path.join(config.OUTPUT_DIR, "comments_analizados.csv")

SUPABASE_PLACEHOLDERS = ("tu-proyecto", "tu-anon-key-de-supabase", "")


def _supabase_client() -> Client | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase: credenciales ausentes, modo sin persistencia en la nube.")
        return None
    if any(p and p in SUPABASE_URL for p in SUPABASE_PLACEHOLDERS if p):
        logger.warning("Supabase: URL es un placeholder, modo sin persistencia en la nube.")
        return None
    try:
        logger.info("Conectando a Supabase...")
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Supabase: conexión falló ({e}), modo sin persistencia.")
        return None


supabase: Client | None = _supabase_client()

app = FastAPI(title="API Sarcasmo Colombiano")

# ── CORS: solo localhost del dashboard ───────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Lock para serializar escrituras al CSV (evita race conditions)
_csv_lock = asyncio.Lock()

# Limite razonable del texto del comentario
MAX_TEXT_LEN = 5000
SENTIMIENTOS_VALIDOS = {"Positivo", "Neutral", "Negativo"}


# ── Modelos ──────────────────────────────────────────────────────────────────
class ComentarioRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)


class UpdateCommentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    sentiment: str = Field(..., min_length=1, max_length=20)


# ── Lógica del clasificador ─────────────────────────────────────────────────
async def analizar_sarcasmo_llm(comentario: str) -> dict:
    """Clasificador determinista basado en reglas colombianas (no usa LLM)."""
    resultado = analizar_comentario_colombia(comentario)
    return {
        "temperatura": round(min(1.0, max(0.0, float(resultado["temperatura"]))), 2),
        "tipo_humor": resultado["tipo_humor"],
        "justificacion": resultado["justificacion"],
        "categoria": resultado["categoria"],
        "palabra_clave": resultado["palabra_clave"],
    }


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supabase": bool(supabase),
        "csv_existe": os.path.exists(COMMENTS_CSV),
    }


@app.post("/analizar/")
async def analizar_comentario(req: ComentarioRequest):
    try:
        analisis = await analizar_sarcasmo_llm(req.texto)

        if supabase:
            try:
                supabase.table("analisis_comentarios").insert({
                    "comentario_original": req.texto,
                    "calificacion_temperatura": analisis["temperatura"],
                    "tipo_humor": analisis["tipo_humor"],
                    "justificacion": analisis["justificacion"],
                }).execute()
            except Exception as e:
                logger.warning(f"No se pudo guardar en Supabase: {e}")

        return {
            "status": "success",
            "data": analisis,
            "guardado_supabase": bool(supabase),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en /analizar/")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update_comment/")
async def update_comment(req: UpdateCommentRequest):
    if req.sentiment not in SENTIMIENTOS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"sentiment debe ser uno de: {sorted(SENTIMIENTOS_VALIDOS)}",
        )

    if not os.path.exists(COMMENTS_CSV):
        raise HTTPException(status_code=404, detail="CSV no encontrado")

    async with _csv_lock:
        try:
            df = await asyncio.to_thread(pd.read_csv, COMMENTS_CSV, encoding="utf-8-sig")
            mask = df["comment_text"] == req.text
            filas = int(mask.sum())
            if filas == 0:
                return {"status": "noop", "message": "Comentario no encontrado en CSV", "rows": 0}
            df.loc[mask, "sentimiento"] = req.sentiment
            await asyncio.to_thread(
                df.to_csv, COMMENTS_CSV, index=False, encoding="utf-8-sig"
            )
            logger.info(f"update_comment: {filas} fila(s) → {req.sentiment}")
            return {
                "status": "success",
                "message": f"Persistido: {req.sentiment}",
                "rows": filas,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error en /update_comment/")
            raise HTTPException(status_code=500, detail=str(e))
