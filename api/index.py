import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

# Importamos tu lógica de moderación
from moderacion_colombia import analizar_comentario_colombia

load_dotenv()

app = FastAPI()

# Permitir CORS para que el dashboard pueda llamar a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_supabase() -> Client | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except:
        return None

class ComentarioRequest(BaseModel):
    texto: str

@app.get("/api/health")
async def health():
    return {"status": "ok", "cloud": True}

class UpdateCommentRequest(BaseModel):
    text: str
    sentiment: str

@app.post("/api/analizar/")
@app.post("/api/analizar")
async def analizar_comentario(req: ComentarioRequest):
    try:
        # Ejecutar la lógica de sarcasmo colombiano
        analisis = analizar_comentario_colombia(req.texto)
        
        # Formatear respuesta
        res = {
            "temperatura": round(float(analisis["temperatura"]), 2),
            "tipo_humor": analisis["tipo_humor"],
            "justificacion": analisis["justificacion"],
            "categoria": analisis["categoria"]
        }

        # Intentar guardar en Supabase si está configurado
        supabase = get_supabase()
        if supabase:
            try:
                supabase.table("comentarios").insert({
                    "comentario": req.texto,
                    "sentimiento": analisis["categoria"],
                    # Si tienes columnas para temperatura o tipo_humor, puedes añadirlas aquí
                }).execute()
            except:
                pass

        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update_comment/")
@app.post("/api/update_comment")
async def update_comment(req: UpdateCommentRequest):
    """
    En la nube, no podemos escribir en el CSV local. 
    Este endpoint intentará actualizar el sentimiento en Supabase.
    """
    supabase = get_supabase()
    if not supabase:
        return {"status": "noop", "message": "Supabase no configurado, no se puede actualizar en la nube."}
    
    try:
        # Actualizar el sentimiento en la tabla 'comentarios'
        supabase.table("comentarios").update({
            "sentimiento": req.sentiment
        }).eq("comentario", req.text).execute()
        
        return {"status": "success", "message": f"Actualizado en Supabase: {req.sentiment}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
