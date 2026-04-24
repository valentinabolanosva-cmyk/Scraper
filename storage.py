"""
=====================================
  MÓDULO DE ALMACENAMIENTO v2
  Dos archivos CSV relacionados:
   - posts_summary.csv   (1 fila por post)
   - comments.csv        (1 fila por comentario)
=====================================
"""

import os
import json
import csv
import logging
from datetime import datetime
from config import OUTPUT_DIR, LOG_FILE, CHECKPOINT

# ── Rutas de salida ────────────────────────────────────────────────────────────
OUTPUT_POSTS_CSV    = os.path.join(OUTPUT_DIR, "posts_summary.csv")
OUTPUT_COMMENTS_CSV = os.path.join(OUTPUT_DIR, "comments.csv")
OUTPUT_POSTS_JSON   = os.path.join(OUTPUT_DIR, "posts_summary.json")
OUTPUT_COMMENTS_JSON= os.path.join(OUTPUT_DIR, "comments.json")


def setup_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "logs"), exist_ok=True)


def setup_logging():
    setup_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("FacebookScraper")


# ════════════════════════════════════════════════════════════════
#  CSV DE POSTS (resumen por publicación)
# ════════════════════════════════════════════════════════════════

POST_HEADERS = [
    "post_url",
    "post_date",
    "post_type",       # foto / video / post
    "post_text",
    "total_likes",
    "total_comments",
    "total_shares",
    "total_views",
    "comments_scraped",  # cuántos comentarios se extrajeron realmente
    "scraped_at",
]


def init_posts_csv():
    setup_dirs()
    if not os.path.exists(OUTPUT_POSTS_CSV):
        with open(OUTPUT_POSTS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=POST_HEADERS)
            writer.writeheader()


def save_post_summary(post: dict, logger=None):
    """Guarda el resumen de un post (métricas generales)."""
    try:
        init_posts_csv()
        post["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(OUTPUT_POSTS_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=POST_HEADERS, extrasaction="ignore")
            writer.writerow(post)
        _append_json(OUTPUT_POSTS_JSON, post)
        return True
    except Exception as e:
        if logger:
            logger.error(f"Error guardando post: {e}")
        return False


# ════════════════════════════════════════════════════════════════
#  CSV DE COMENTARIOS (1 fila por comentario)
# ════════════════════════════════════════════════════════════════

COMMENT_HEADERS = [
    "post_url",        # FK → posts_summary
    "post_date",
    "post_type",
    "comment_order",   # orden del comentario dentro del post (1, 2, 3...)
    "commenter_name",  # nombre de quien comentó
    "comment_text",    # texto del comentario
    "comment_likes",   # likes que recibió ese comentario
    "comment_date",    # fecha del comentario (si está disponible)
    "is_reply",        # True si es respuesta a otro comentario
    "scraped_at",
]


def init_comments_csv():
    setup_dirs()
    if not os.path.exists(OUTPUT_COMMENTS_CSV):
        with open(OUTPUT_COMMENTS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COMMENT_HEADERS)
            writer.writeheader()


def save_comments_batch(comments: list, logger=None):
    """
    Guarda todos los comentarios de un post de golpe.
    comments: lista de dicts con los campos de COMMENT_HEADERS
    """
    if not comments:
        return 0
    try:
        init_comments_csv()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(OUTPUT_COMMENTS_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COMMENT_HEADERS, extrasaction="ignore")
            for c in comments:
                c["scraped_at"] = now
                writer.writerow(c)
        _append_json(OUTPUT_COMMENTS_JSON, comments)
        if logger:
            logger.info(f"   Guardados {len(comments)} comentarios")
        return len(comments)
    except Exception as e:
        if logger:
            logger.error(f"Error guardando comentarios: {e}")
        return 0


# ════════════════════════════════════════════════════════════════
#  UTILIDADES COMPARTIDAS
# ════════════════════════════════════════════════════════════════

def _append_json(path: str, data):
    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    if isinstance(data, list):
        existing.extend(data)
    else:
        existing.append(data)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def load_scraped_urls() -> set:
    """Carga las URLs de posts ya procesados para no repetir."""
    scraped = set()
    if os.path.exists(OUTPUT_POSTS_CSV):
        try:
            with open(OUTPUT_POSTS_CSV, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("post_url", "").strip()
                    if url:
                        scraped.add(url)
        except Exception:
            pass
    return scraped


def save_checkpoint(section: str, scroll_count: int):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        f.write(f"{section}:{scroll_count}")


def load_checkpoint() -> tuple:
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT, "r", encoding="utf-8") as f:
                content = f.read().strip()
                section, count = content.split(":")
                return section, int(count)
        except Exception:
            pass
    return None, 0


def get_stats() -> dict:
    stats = {"posts": 0, "comments": 0}
    if os.path.exists(OUTPUT_POSTS_CSV):
        try:
            with open(OUTPUT_POSTS_CSV, "r", encoding="utf-8-sig") as f:
                stats["posts"] = sum(1 for _ in csv.DictReader(f))
        except Exception:
            pass
    if os.path.exists(OUTPUT_COMMENTS_CSV):
        try:
            with open(OUTPUT_COMMENTS_CSV, "r", encoding="utf-8-sig") as f:
                stats["comments"] = sum(1 for _ in csv.DictReader(f))
        except Exception:
            pass
    return stats
