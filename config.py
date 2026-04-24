"""
=====================================
  CONFIGURACIÓN DEL SCRAPER
  Edita este archivo antes de correr
=====================================
"""

import os

# ── URL Objetivo ──────────────────────────────────────────────────────────────
PAGE_URL = "https://www.facebook.com/LaPolemicaDelHuila"

# ══════════════════════════════════════════════════════════════════
#  SESIÓN DE CHROME EXISTENTE  ← RECOMENDADO (sin crear cuenta)
# ══════════════════════════════════════════════════════════════════
# El scraper usa tu Chrome donde ya tienes Facebook abierto.
# NO necesitas dar contraseñas ni crear cuentas nuevas.
#
# Pasos:
#  1. Asegúrate de estar LOGUEADO en Facebook en tu Chrome normal
#  2. CIERRA completamente Chrome antes de ejecutar el scraper
#     (Chrome no puede estar abierto al mismo tiempo)
#  3. Ejecuta: python scraper.py
#
USE_CHROME_SESSION = True   # True = usar tu Chrome actual (recomendado)

# Ruta al perfil de Chrome — detección automática, no tocar salvo error
_chrome_base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
CHROME_USER_DATA = _chrome_base if os.path.exists(_chrome_base) else ""
CHROME_PROFILE   = "Default"   # Perfil de Chrome (casi siempre "Default")

# ── Credenciales de Facebook (ALTERNATIVA si no usas Chrome session) ──────────
# Solo si USE_CHROME_SESSION = False
FB_EMAIL    = ""
FB_PASSWORD = ""

# ── Proxies ───────────────────────────────────────────────────────────────────
USE_PROXY = False
PROXY_ROTATION_EVERY = 10
MANUAL_PROXIES = []

# ── Comportamiento Anti-Detección ─────────────────────────────────────────────
HEADLESS       = False
MIN_DELAY      = 2.5
MAX_DELAY      = 6.0
SCROLL_PAUSE   = 2.0
MAX_RETRIES    = 3
SCROLL_AMOUNT  = 800

# ── Secciones a scrapear ──────────────────────────────────────────────────────
SCRAPE_PHOTOS  = True
SCRAPE_VIDEOS  = True
SCRAPE_POSTS   = True

# ── Salida de datos ───────────────────────────────────────────────────────────
OUTPUT_DIR  = "output"
LOG_FILE    = "output/logs/scraper.log"
CHECKPOINT = "output/checkpoint.txt"

# ── Límites (0 = sin límite) ──────────────────────────────────────────────────
MAX_POSTS = 0  # 0 = todos los posts
