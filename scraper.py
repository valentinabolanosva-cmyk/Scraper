"""
=====================================
  FACEBOOK SCRAPER v3 — SIN LÍMITES
  Página : LaPolemicaDelHuila
  Método : Interceptación GraphQL
           (captura el JSON interno
            que Facebook envía a su
            propio cliente)
  + Mobile site (m.facebook.com)
  + Sin límite de comentarios
  + Sin límite de scroll
=====================================
"""

import asyncio
import json
import os
import random
import re
import threading
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse, urlencode, urljoin

from playwright.async_api import (
    async_playwright, Page, Route, Request,
    TimeoutError as PwTimeoutError
)

import config
from storage import (
    setup_logging,
    init_posts_csv, init_comments_csv,
    save_post_summary, save_comments_batch,
    load_scraped_urls, save_checkpoint, get_stats
)
from proxies import ProxyRotator

logger = setup_logging()

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "output", "browser_profile")

# Usamos la versión MÓVIL de Facebook — mucho menos restrictiva
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Mobile Safari/537.36"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ════════════════════════════════════════════════════════════════
#   UTILIDADES
# ════════════════════════════════════════════════════════════════

async def human_delay(min_s: float = None, max_s: float = None):
    lo = min_s if min_s is not None else config.MIN_DELAY
    hi = max_s if max_s is not None else config.MAX_DELAY
    await asyncio.sleep(random.uniform(lo, hi))


async def human_scroll(page: Page, times: int = 1):
    for _ in range(times):
        delta = random.randint(config.SCROLL_AMOUNT - 200, config.SCROLL_AMOUNT + 200)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.3, 0.8))


async def random_mouse_move(page: Page):
    x = random.randint(100, 1300)
    y = random.randint(100, 700)
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.1, 0.3))


def parse_count(text: str) -> int:
    if not text:
        return 0
    text = str(text).strip()
    text = re.sub(r"[^\d.,KkMmBb]", "", text)
    text = text.upper().replace(",", ".")
    mult = 1
    if text.endswith("K"):
        mult = 1_000; text = text[:-1]
    elif text.endswith("M"):
        mult = 1_000_000; text = text[:-1]
    elif text.endswith("B"):
        mult = 1_000_000_000; text = text[:-1]
    parts = text.split(".")
    text = parts[0] + ("." + "".join(parts[1:]) if len(parts) > 1 else "")
    try:
        return int(float(text) * mult)
    except ValueError:
        return 0


def to_mobile_url(url: str) -> str:
    """Convierte cualquier URL de facebook.com a m.facebook.com"""
    return url.replace("https://www.facebook.com", "https://m.facebook.com") \
              .replace("https://facebook.com", "https://m.facebook.com")


# ════════════════════════════════════════════════════════════════
#   ANTI-BLOQUEO
# ════════════════════════════════════════════════════════════════

async def kill_overlay(page: Page):
    """Remueve overlays y restaura el scroll — se llama en cada iteración."""
    try:
        await page.evaluate("""
        () => {
            document.querySelectorAll('*').forEach(el => {
                const s = window.getComputedStyle(el);
                const z = parseInt(s.zIndex) || 0;
                if ((s.position==='fixed'||s.position==='sticky') && z>100) {
                    if (el.getAttribute('role')!=='navigation' && el.tagName!=='NAV')
                        el.remove();
                }
            });
            document.body.style.overflow = 'visible';
            document.body.style.height   = 'auto';
            document.documentElement.style.overflow = 'visible';
            document.querySelectorAll('[inert]').forEach(e => e.removeAttribute('inert'));
            document.querySelectorAll('[aria-hidden="true"]').forEach(e => {
                if(e.children.length > 2) e.removeAttribute('aria-hidden');
            });
        }
        """)
    except Exception:
        pass


async def close_popups(page: Page):
    for sel in ["[aria-label='Cerrar']", "[aria-label='Close']",
                "[data-cookiebanner='accept_button']",
                "div[role='dialog'] [aria-label='Cerrar']"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=1_000)
                await asyncio.sleep(0.2)
        except Exception:
            pass
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.2)
    except Exception:
        pass
    await kill_overlay(page)


# ════════════════════════════════════════════════════════════════
#   BROWSER SETUP
# ════════════════════════════════════════════════════════════════

async def create_browser(playwright, proxy: dict = None, mobile: bool = False):
    """
    Lanza el navegador. Si USE_CHROME_SESSION=True, usa el perfil de
    Chrome del usuario donde ya tiene Facebook logueado — sin necesidad
    de credenciales ni cuenta nueva.
    IMPORTANTE: Chrome debe estar cerrado antes de ejecutar.
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)

    common_args = [
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--disable-popup-blocking",
        "--disable-features=IsolateOrigins,site-per-process",
        "--window-size=1920,1080",
    ]

    anti_detect_script = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',   { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['es-CO','es','en-US'] });
        Object.defineProperty(navigator, 'platform',  { get: () => 'Win32' });
        window.chrome = { runtime: {}, loadTimes: ()=>{}, csi: ()=>{} };
        const _obs = new MutationObserver(ms => {
            ms.forEach(m => m.addedNodes.forEach(n => {
                if(n.nodeType!==1) return;
                const s = window.getComputedStyle(n);
                if((s.position==='fixed'||s.position==='sticky')
                    && parseInt(s.zIndex)>100
                    && n.getAttribute('role')!=='navigation') n.remove();
            }));
            document.body.style.overflow='visible';
            document.body.style.height='auto';
        });
        document.body
            ? _obs.observe(document.body,{childList:true,subtree:true})
            : document.addEventListener('DOMContentLoaded',()=>
                _obs.observe(document.body,{childList:true,subtree:true}));
    """

    # ── Modo: usar perfil existente de Chrome ──────────────────────────────────
    if config.USE_CHROME_SESSION and config.CHROME_USER_DATA:
        import shutil

        src_profile = os.path.join(config.CHROME_USER_DATA, config.CHROME_PROFILE)
        dst_profile_dir = os.path.join(os.path.dirname(__file__), "output", "chrome_profile_copy")
        dst_profile = os.path.join(dst_profile_dir, config.CHROME_PROFILE)

        # Copiar el perfil solo si no existe copia previa o si hay sesión reciente
        if not os.path.exists(dst_profile):
            logger.info(f"Copiando perfil de Chrome (primera vez, puede tardar 1-2 min)...")
            if os.path.exists(src_profile):
                shutil.copytree(src_profile, dst_profile,
                    ignore=shutil.ignore_patterns(
                        "*.log", "*.tmp", "GPUCache", "ShaderCache",
                        "Code Cache", "blob_storage", "databases"
                    )
                )
                logger.info(f"Perfil copiado a: {dst_profile}")
            else:
                logger.warning(f"No se encontro perfil en: {src_profile}")
                logger.warning("Continuando sin sesion de Chrome...")
                config.USE_CHROME_SESSION = False

        if config.USE_CHROME_SESSION:
            logger.info(f"Lanzando Chrome con perfil copiado — sesion de Facebook activa")
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=dst_profile_dir,
                channel="chrome",
                headless=config.HEADLESS,
                args=common_args + [f"--profile-directory={config.CHROME_PROFILE}"],
                proxy=proxy,
                viewport={"width": 1920, "height": 1080},
                locale="es-CO",
                timezone_id="America/Bogota",
                java_script_enabled=True,
                bypass_csp=True,
            )
            await context.add_init_script(anti_detect_script)
            return None, context


    # ── Modo: navegador limpio con credenciales ────────────────────────────────
    browser = await playwright.chromium.launch(
        headless=config.HEADLESS,
        args=common_args,
        proxy=proxy,
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=DESKTOP_UA,
        locale="es-CO",
        timezone_id="America/Bogota",
        extra_http_headers={
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
        java_script_enabled=True,
        bypass_csp=True,
    )
    await context.add_init_script(anti_detect_script)
    return browser, context


# ════════════════════════════════════════════════════════════════
#   LOGIN
# ════════════════════════════════════════════════════════════════

async def facebook_login(page: Page, mobile: bool = False) -> bool:
    if not config.FB_EMAIL or not config.FB_PASSWORD:
        logger.info("Sin credenciales — modo publico")
        return False
    login_url = "https://m.facebook.com/login" if mobile else "https://www.facebook.com/login"
    logger.info(f"Iniciando sesion en Facebook ({'mobile' if mobile else 'desktop'})...")
    try:
        await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
        await human_delay(2, 3)
        email_input = await page.wait_for_selector("#email,input[name='email']", timeout=10_000)
        await email_input.click()
        await email_input.type(config.FB_EMAIL, delay=random.randint(50, 120))
        await human_delay(0.5, 1)
        pass_input = page.locator("#pass,input[name='pass']").first
        await pass_input.click()
        await pass_input.type(config.FB_PASSWORD, delay=random.randint(50, 120))
        await human_delay(0.5, 1.5)
        await page.locator("button[name='login'],input[name='login']").first.click()
        await page.wait_for_load_state("networkidle", timeout=30_000)
        await human_delay(3, 5)
        if "login" not in page.url and "checkpoint" not in page.url:
            logger.info("Login exitoso")
            return True
        logger.warning(f"Login posiblemente fallido — {page.url}")
        return False
    except Exception as e:
        logger.error(f"Error en login: {e}")
        return False


# ════════════════════════════════════════════════════════════════
#   INTERCEPTACIÓN GRAPHQL — CORAZÓN DEL MÉTODO SIN LÍMITES
# ════════════════════════════════════════════════════════════════

class GraphQLCommentCollector:
    """
    Intercepta las llamadas GraphQL que Facebook hace internamente
    para cargar comentarios. Extrae los datos directamente del JSON
    que Facebook envía a su propio cliente — sin pasar por el DOM,
    sin límites de vista, sin login wall.
    """

    def __init__(self):
        self._comments: list = []
        self._lock = asyncio.Lock()

    def reset(self):
        self._comments = []

    async def get_comments(self) -> list:
        async with self._lock:
            return list(self._comments)

    async def handle_response(self, response):
        """Procesa cada respuesta que devuelve el servidor de Facebook."""
        url = response.url
        # Solo nos interesan las respuestas GraphQL de Facebook
        if "graphql" not in url and "api/graphql" not in url:
            return
        try:
            text = await response.text()
        except Exception:
            return

        # Facebook a veces devuelve múltiples objetos JSON separados por newline
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                await self._parse_graphql_json(data)
            except json.JSONDecodeError:
                pass

    async def _parse_graphql_json(self, data: dict):
        """
        Recorre recursivamente el JSON de GraphQL buscando nodos
        de tipo Comment con sus campos.
        """
        if not isinstance(data, dict):
            return

        found = []

        def walk(obj):
            if isinstance(obj, dict):
                # Identificar nodos que son comentarios
                if obj.get("__typename") in ("Comment", "CommentNode"):
                    comment = self._extract_comment_node(obj)
                    if comment:
                        found.append(comment)
                    # También buscar replies dentro
                    replies_edge = obj.get("feedback", {}).get("replies", {})
                    if replies_edge:
                        walk(replies_edge)
                else:
                    for v in obj.values():
                        walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)

        if found:
            async with self._lock:
                self._comments.extend(found)

    @staticmethod
    def _extract_comment_node(node: dict) -> dict | None:
        """Extrae campos relevantes de un nodo Comment de GraphQL."""
        try:
            # Texto
            body = node.get("body") or node.get("message") or {}
            if isinstance(body, dict):
                text = body.get("text", "") or body.get("delight_ranges", [{}])[0].get("entity", {}).get("name", "")
            else:
                text = str(body)

            # Autor
            author = node.get("author") or node.get("commenter") or {}
            if isinstance(author, dict):
                name = author.get("name", "") or author.get("__name", "")
            else:
                name = str(author)

            # Likes del comentario
            feedback = node.get("feedback") or {}
            likes = 0
            if isinstance(feedback, dict):
                reaction_count = feedback.get("reaction_count") or {}
                if isinstance(reaction_count, dict):
                    likes = reaction_count.get("count", 0) or 0
                # Alternativa
                if not likes:
                    likes = feedback.get("reactors", {}).get("count", 0) or 0

            # Fecha
            created = node.get("created_time") or node.get("timestamp", {})
            if isinstance(created, dict):
                ts = created.get("text", "") or str(created.get("time", ""))
            else:
                ts = str(created) if created else ""

            # ¿Es reply?
            is_reply = bool(node.get("parent_comment") or node.get("is_reply"))

            if not text and not name:
                return None

            return {
                "commenter_name": name.strip(),
                "comment_text":   text.strip()[:1000],
                "comment_likes":  int(likes),
                "comment_date":   ts.strip(),
                "is_reply":       is_reply,
            }
        except Exception:
            return None


# ════════════════════════════════════════════════════════════════
#   CLIC EN "VER MÁS COMENTARIOS" DE FORMA EXHAUSTIVA
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
#   MATAR SOLO EL LOGIN WALL (versión suave — no borra métricas)
# ════════════════════════════════════════════════════════════════

async def kill_login_wall_only(page: Page):
    """
    Versión suave de kill_overlay: solo elimina el modal de login
    de Facebook, NO toca elementos de reacciones ni comentarios.
    """
    try:
        await page.evaluate("""
        () => {
            // Solo borrar divs que contengan formularios de login o sean el dimmer
            document.querySelectorAll('div[role="dialog"], div[data-nosnippet]').forEach(el => {
                const s = window.getComputedStyle(el);
                if (parseInt(s.zIndex) > 200) el.remove();
            });
            // Restaurar scroll bloqueado
            document.body.style.overflow    = 'visible';
            document.body.style.height      = 'auto';
            document.documentElement.style.overflow = 'visible';
            document.querySelectorAll('[inert]').forEach(e => e.removeAttribute('inert'));
        }
        """)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
#   EXTRAER MÉTRICAS CON JS — BUSCA TEXTO VISIBLE EN LA PÁGINA
# ════════════════════════════════════════════════════════════════

async def extract_metrics_js(page: Page, post_type: str) -> dict:
    """
    Extrae likes, comentarios, shares y vistas usando JavaScript
    que lee el texto visible de la página — más robusto que CSS selectors
    en el Facebook actual que cambia clases continuamente.
    """
    result = await page.evaluate("""
    () => {
        const data = {
            likes: 0, comments: 0, shares: 0, views: 0,
            post_text: '', post_date: ''
        };

        // ── 1. MÉTRICAS desde aria-labels de botones de reacción ─────────────
        // En fotos (lightbox), el número de likes está en el aria-label del botón
        const allEls = [...document.querySelectorAll('[aria-label]')];
        for (const el of allEls) {
            const lbl = el.getAttribute('aria-label') || '';
            if (!data.likes) {
                const m = lbl.match(/^([\d,.]+)\s*(mil|K|M)?\s*(persona|reacci|reaccion)/i)
                       || lbl.match(/reacci[oó]n.*?·\s*([\d,.]+)/i)
                       || lbl.match(/^([\d,.]+)$/);
                if (m) {
                    const n = (m[1]||'').replace(',','.').replace(/\s/g,'');
                    const mult = /mil|K/i.test(m[2]||'') ? 1000 : /M/i.test(m[2]||'') ? 1000000 : 1;
                    const v = Math.round(parseFloat(n) * mult);
                    if (v > 0 && v < 100000000) data.likes = v;
                }
            }
        }

        // ── 2. MÉTRICAS desde texto visible ──────────────────────────────
        const allText = document.body.innerText;

        // Reacciones: buscar número antes de "reacci" o "Me gusta"
        if (!data.likes) {
            const reactMatch = allText.match(/([\d,.]+\s*(mil|K|M)?)\s*(reacciones|reacción|Me gusta)/i);
            if (reactMatch) {
                let n = reactMatch[1].replace(/\s/g,'').replace(',','.');
                const mult = /mil|K/i.test(reactMatch[2]) ? 1000 :
                             /M/i.test(reactMatch[2]) ? 1000000 : 1;
                data.likes = Math.round(parseFloat(n) * mult) || 0;
            }
        }

        // Comentarios: buscar número antes de "comentario"
        if (!data.comments) {
            const cmtMatch = allText.match(/([\d,.]+\s*(mil|K|M)?)\s*comentario/i);
            if (cmtMatch) {
                let n = cmtMatch[1].replace(/\s/g,'').replace(',','.');
                const mult = /mil|K/i.test(cmtMatch[2]) ? 1000 :
                             /M/i.test(cmtMatch[2]) ? 1000000 : 1;
                data.comments = Math.round(parseFloat(n) * mult) || 0;
            }
        }

        // Compartidos: buscar número antes de "compartido" o "veces compartido"
        if (!data.shares) {
            const shareMatch = allText.match(/([\d,.]+\s*(mil|K|M)?)\s*(veces\s+)?compartido/i);
            if (shareMatch) {
                let n = shareMatch[1].replace(/\s/g,'').replace(',','.');
                const mult = /mil|K/i.test(shareMatch[2]) ? 1000 :
                             /M/i.test(shareMatch[2]) ? 1000000 : 1;
                data.shares = Math.round(parseFloat(n) * mult) || 0;
            }
        }

        // Reproducciones: buscar número antes de "reproduc" o "vista"
        if (!data.views) {
            const viewMatch = allText.match(/([\d,.]+\s*(mil|K|M)?)\s*(reproduc|vistas?)/i);
            if (viewMatch) {
                let n = viewMatch[1].replace(/\s/g,'').replace(',','.');
                const mult = /mil|K/i.test(viewMatch[2]) ? 1000 :
                             /M/i.test(viewMatch[2]) ? 1000000 : 1;
                data.views = Math.round(parseFloat(n) * mult) || 0;
            }
        }

        // ── 3. MÉTRICAS desde JSON embebido en la página ──────────────────
        const scripts = [...document.querySelectorAll('script')];
        for (const s of scripts) {
            const t = s.textContent || '';
            if (!data.likes) {
                const rm = t.match(/"reaction_count"\s*:\s*\{"count"\s*:\s*(\d+)/);
                if (rm) data.likes = parseInt(rm[1]);
            }
            if (!data.comments) {
                const cm = t.match(/"comment_count"\s*:\s*\{"total_count"\s*:\s*(\d+)/) || t.match(/"total_count"\s*:\s*(\d+)/);
                if (cm) data.comments = parseInt(cm[1]);
            }
            if (!data.shares) {
                const sm = t.match(/"share_count"\s*:\s*\{"count"\s*:\s*(\d+)/);
                if (sm) data.shares = parseInt(sm[1]);
            }
            if (!data.views) {
                const vm = t.match(/"video_view_count"\s*:\s*(\d+)/) || t.match(/"view_count"\s*:\s*(\d+)/);
                if (vm) data.views = parseInt(vm[1]);
            }
            if (data.likes && data.comments) break;
        }

        // ── 3. FECHA del post ─────────────────────────────────────────────
        for (const sel of ['abbr[data-utime]', 'abbr[title]', 'time[datetime]', 'a[aria-label] abbr']) {
            const el = document.querySelector(sel);
            if (el) {
                data.post_date = el.getAttribute('title') || el.getAttribute('datetime') || el.innerText;
                break;
            }
        }

        // ── 4. TEXTO del post ─────────────────────────────────────────────
        for (const sel of [
            'div[data-ad-preview="message"]',
            'div[dir="auto"] > div[dir="auto"]',
            'div[class*="userContent"]',
            '[data-testid="post_message"]',
        ]) {
            const el = document.querySelector(sel);
            if (el && el.innerText.trim().length > 0) {
                data.post_text = el.innerText.trim().substring(0, 500);
                break;
            }
        }

        return data;
    }
    """)

    return {
        "post_date":      str(result.get("post_date", "") or "").strip(),
        "post_text":      str(result.get("post_text", "") or "").strip(),
        "total_likes":    int(result.get("likes", 0) or 0),
        "total_comments": int(result.get("comments", 0) or 0),
        "total_shares":   int(result.get("shares", 0) or 0),
        "total_views":    int(result.get("views", 0) or 0),
    }


# ════════════════════════════════════════════════════════════════
#   CLIC EN "VER MÁS COMENTARIOS"
# ════════════════════════════════════════════════════════════════

async def click_all_load_more(page: Page, collector: "GraphQLCommentCollector"):
    """
    Hace clic en todos los botones 'Ver más comentarios' y 'Ver respuestas'
    hasta que no queden más. El interceptor GraphQL captura cada lote.
    """
    MAX_CLICKS = 300
    clicks = 0
    consecutive_no_btn = 0

    keywords_more = ["ver más comentarios", "ver todos los comentarios",
                     "view more comments", "mostrar más comentarios"]
    keywords_reply = ["ver respuesta", "ver respuestas", "view replies",
                      "mostrar respuestas"]

    while clicks < MAX_CLICKS:
        clicked = False

        # Buscar botón "ver más comentarios"
        try:
            all_btns = await page.locator("div[role='button'], span[role='button'], a").all()
            for btn in all_btns:
                try:
                    txt = (await btn.inner_text(timeout=300)).lower().strip()
                    if any(kw in txt for kw in keywords_more + keywords_reply):
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.4)
                        await btn.click(timeout=3_000)
                        await asyncio.sleep(random.uniform(1.5, 2.5))
                        clicks += 1
                        clicked = True
                        logger.info(f"   Clic #{clicks} '{txt[:30]}' | GraphQL comments: {len(await collector.get_comments())}")
                        break
                except Exception:
                    pass
        except Exception:
            pass

        if clicked:
            consecutive_no_btn = 0
            # Scroll gentil para revelar más botones
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(0.5)
        else:
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(0.8)
            consecutive_no_btn += 1
            if consecutive_no_btn >= 4:
                logger.info(f"   Fin de comentarios. Total clics: {clicks}")
                break

    return clicks


# ════════════════════════════════════════════════════════════════
#   EXTRACCIÓN DE COMENTARIOS DEL DOM
# ════════════════════════════════════════════════════════════════

async def extract_comments_from_dom(page: Page) -> list:
    """
    Extrae todos los comentarios visibles del DOM.
    Usa div[role='article'] confirmado como contenedor de comentarios
    en el Facebook actual (2024).
    """
    return await page.evaluate("""
    () => {
        const results = [];
        const seen = new Set();

        // Cada comentario está en un div[role='article']
        const articles = [...document.querySelectorAll('div[role="article"]')];

        for (const el of articles) {
            try {
                // ── Nombre del comentarista ──────────────────────────────
                let name = '';
                // El nombre es el primer enlace con texto dentro del article
                const links = el.querySelectorAll('a[href*="facebook.com"]');
                for (const a of links) {
                    const t = a.innerText.trim();
                    if (t && t.length > 1 && t.length < 80 && !t.includes('@')) {
                        name = t;
                        break;
                    }
                }

                // ── Texto del comentario ──────────────────────────────────
                let text = '';
                // El texto está en un div/span con dir="auto"
                const textEls = el.querySelectorAll('div[dir="auto"], span[dir="auto"]');
                for (const t of textEls) {
                    const candidate = t.innerText.trim();
                    // Excluir el nombre y elementos muy cortos o de UI
                    if (candidate && candidate !== name
                        && candidate.length > 1
                        && !['Me gusta', 'Responder', 'Ver más', 'Editar'].includes(candidate)) {
                        text = candidate.substring(0, 1000);
                        break;
                    }
                }

                // ── Likes del comentario ──────────────────────────────────
                let likes = 0;
                // Los likes del comentario aparecen como número solo
                // en un span que sigue al ícono de reacción
                const likeSpans = el.querySelectorAll('span');
                for (const sp of likeSpans) {
                    const t = sp.innerText.trim();
                    const aria = sp.getAttribute('aria-label') || '';
                    if (/^\d+$/.test(t) && parseInt(t) > 0) {
                        likes = parseInt(t);
                        break;
                    }
                    if (/reacci/i.test(aria)) {
                        likes = parseInt(aria.replace(/\D/g,'')) || 0;
                        if (likes) break;
                    }
                }

                // ── Fecha del comentario ──────────────────────────────────
                let date = '';
                const dateEl = el.querySelector('a abbr, abbr[title], a[aria-label]');
                if (dateEl) {
                    date = dateEl.getAttribute('title') || dateEl.getAttribute('aria-label') || dateEl.innerText.trim();
                }

                // ── ¿Es respuesta? ─────────────────────────────────────────
                // Las respuestas están anidadas dentro de otro article
                const parentArticle = el.parentElement?.closest('div[role="article"]');
                const isReply = !!parentArticle;

                // ── Deduplicar ─────────────────────────────────────────────
                const key = name + '||' + text.substring(0, 60);
                if (!seen.has(key) && (name || text)) {
                    seen.add(key);
                    results.push({
                        commenter_name: name,
                        comment_text:   text,
                        comment_likes:  likes,
                        comment_date:   date,
                        is_reply:       isReply
                    });
                }
            } catch(e) {}
        }
        return results;
    }
    """)


# ════════════════════════════════════════════════════════════════
#   PROCESAR UN POST COMPLETO
# ════════════════════════════════════════════════════════════════

async def process_post(page: Page, post_url: str, post_type: str) -> bool:
    """
    Abre un post, extrae métricas + todos los comentarios, guarda en CSV.
    """
    for attempt in range(config.MAX_RETRIES):
        try:
            collector = GraphQLCommentCollector()
            collector.reset()
            page.on("response", collector.handle_response)

            logger.info(f"  Cargando (intento {attempt+1}): {post_url}")
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)

            # Esperar a que cargue el contenido principal
            await asyncio.sleep(3)

            # Solo cerrar el modal de login, NO tocar métricas
            await kill_login_wall_only(page)
            await asyncio.sleep(1)

            # ── Extraer métricas usando JS ─────────────────────────────
            metrics = await extract_metrics_js(page, post_type)

            logger.info(
                f"  Metricas: likes={metrics['total_likes']} | "
                f"comentarios={metrics['total_comments']} | "
                f"shares={metrics['total_shares']} | "
                f"vistas={metrics['total_views']}"
            )

            # ── Scroll hasta la sección de comentarios y expandir ─────
            # Scroll hasta el final de la página para llegar a los comentarios
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(1.5)
            await kill_login_wall_only(page)

            total_clicks = await click_all_load_more(page, collector)

            # ── Obtener comentarios ───────────────────────────────────
            graphql_comments = await collector.get_comments()
            try:
                page.remove_listener("response", collector.handle_response)
            except Exception:
                pass

            if graphql_comments:
                logger.info(f"  GraphQL: {len(graphql_comments)} comentarios")
                raw_comments = graphql_comments
            else:
                logger.info("  Extrayendo desde DOM...")
                raw_comments = await extract_comments_from_dom(page)

            # ── Formatear comentarios ─────────────────────────────────
            final_comments = []
            for i, c in enumerate(raw_comments, 1):
                final_comments.append({
                    "post_url":       post_url,
                    "post_date":      metrics["post_date"],
                    "post_type":      post_type,
                    "comment_order":  i,
                    "commenter_name": str(c.get("commenter_name", "") or "").strip(),
                    "comment_text":   str(c.get("comment_text", "") or "").strip()[:1000],
                    "comment_likes":  int(c.get("comment_likes", 0) or 0),
                    "comment_date":   str(c.get("comment_date", "") or "").strip(),
                    "is_reply":       bool(c.get("is_reply", False)),
                })

            # ── Guardar ───────────────────────────────────────────────
            post_summary = {
                "post_url":         post_url,
                "post_date":        metrics["post_date"],
                "post_type":        post_type,
                "post_text":        metrics["post_text"],
                "total_likes":      metrics["total_likes"],
                "total_comments":   metrics["total_comments"],
                "total_shares":     metrics["total_shares"],
                "total_views":      metrics["total_views"],
                "comments_scraped": len(final_comments),
            }
            save_post_summary(post_summary, logger)
            if final_comments:
                save_comments_batch(final_comments, logger)

            logger.info(
                f"  LISTO | likes={metrics['total_likes']} | "
                f"extraidos={len(final_comments)}/{metrics['total_comments']} | "
                f"vistas={metrics['total_views']}"
            )
            return True

        except PwTimeoutError:
            logger.warning(f"  Timeout intento {attempt+1}")
            try: page.remove_listener("response", collector.handle_response)
            except Exception: pass
            await human_delay(5, 10)
        except Exception as e:
            logger.error(f"  Error intento {attempt+1}: {e}")
            try: page.remove_listener("response", collector.handle_response)
            except Exception: pass
            await human_delay(3, 6)

    return False


# ════════════════════════════════════════════════════════════════
#   RECOLECTAR URLs DE POSTS
# ════════════════════════════════════════════════════════════════

async def collect_post_urls(page: Page, section_url: str, post_type: str,
                            already_scraped: set) -> list:
    logger.info(f"\n{'='*60}")
    logger.info(f"Recolectando {post_type.upper()} — {section_url}")
    logger.info(f"{'='*60}")

    # Usamos desktop — mobile redirige de vuelta a desktop sin login
    await page.goto(section_url, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(1.0)

    # Matar overlay inmediatamente al cargar — el contenido SI está en el DOM
    await kill_overlay(page)
    await close_popups(page)
    await asyncio.sleep(0.5)
    # Segunda pasada de limpieza
    await kill_overlay(page)

    collected_urls = []
    seen_urls = set()
    scroll_count = 0
    no_new_count = 0
    MAX_NO_NEW = 500  # más tolerante en mobile

    # Selectores basados en los formatos reales confirmados en el navegador
    if post_type == "photo":
        selectors = [
            "a[href*='photo.php']",       # formato principal: photo.php?fbid=...
            "a[href*='/photo/']",          # formato alternativo
            "a[href*='/photos/']",
        ]
    elif post_type == "video":
        selectors = [
            "a[href*='/videos/']",
            "a[href*='/video/']",
            "a[href*='/reel/']",
            "a[href*='video_id']",
        ]
    else:
        selectors = [
            "a[href*='/posts/']",
            "a[href*='/permalink/'], a[href*='story.php']",
            "a[href*='/pfbid']",
            "a[href*='story_fbid']",
        ]

    while True:
        await kill_overlay(page)

        batch = set()
        for sel in selectors:
            try:
                for el in await page.locator(sel).all():
                    try:
                        href = await el.get_attribute("href")
                        if not href:
                            continue
                        href = href.replace("m.facebook.com", "www.facebook.com")
                        if href.startswith("/"):
                            href = "https://www.facebook.com" + href

                        # Fotos: conservar ?fbid= (es la ID unica de la foto)
                        if post_type == "photo" and "fbid=" in href:
                            base = href.split("&")[0].strip().rstrip("/")
                            if base not in seen_urls:
                                batch.add(base)
                        else:
                            clean = href.split("?")[0].strip().rstrip("/")
                            if clean and "facebook.com" in clean and clean not in seen_urls:
                                batch.add(clean)
                    except Exception:
                        pass
            except Exception:
                pass

        new_this_scroll = 0
        for url in batch:
            if url not in seen_urls:
                collected_urls.append((url, post_type))
                seen_urls.add(url)
                new_this_scroll += 1


        logger.info(
            f"  Scroll #{scroll_count} | Nuevas: {new_this_scroll} | "
            f"Total acumulado: {len(collected_urls)}"
        )

        if config.MAX_POSTS > 0 and len(collected_urls) >= config.MAX_POSTS:
            break

        if new_this_scroll == 0:
            no_new_count += 1
            if no_new_count >= MAX_NO_NEW:
                logger.info(f"  Fin de seccion tras {MAX_NO_NEW} scrolls sin nuevas URLs")
                break
        else:
            no_new_count = 0

        await random_mouse_move(page)
        await human_scroll(page, times=10)
        await asyncio.sleep(config.SCROLL_PAUSE)
        save_checkpoint(post_type, scroll_count)
        scroll_count += 1

        if scroll_count % 3 == 0:
            await kill_overlay(page)
            await close_popups(page)

    logger.info(f"URLs de {post_type}: {len(collected_urls)}")
    return collected_urls


# ════════════════════════════════════════════════════════════════
#   SCRAPER PRINCIPAL
# ════════════════════════════════════════════════════════════════

async def run_scraper():
    print("\n" + "="*60)
    print("  FACEBOOK SCRAPER v3 — SIN LIMITES")
    print("  Metodo: GraphQL Intercept + Mobile Site")
    print("="*60 + "\n")

    init_posts_csv()
    init_comments_csv()
    already_scraped = load_scraped_urls()
    stats_start = get_stats()
    logger.info(f"Posts ya procesados : {stats_start['posts']}")
    logger.info(f"Comentarios en CSV  : {stats_start['comments']}")
    logger.info(f"URLs ya scrapeadas  : {len(already_scraped)}")

    proxy_rotator = ProxyRotator()
    proxy_rotator.load()
    proxy = proxy_rotator.get_next()

    async with async_playwright() as pw:
        browser, context = await create_browser(pw, proxy, mobile=True)
        page = await context.new_page()

        try:
            # Si usamos Chrome session ya estamos logueados automaticamente
            if config.USE_CHROME_SESSION:
                logger.info("Modo Chrome session — verificando login en Facebook...")
                await page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=20_000)
                await human_delay(2, 3)
                await kill_overlay(page)
                logged_in = "login" not in page.url and "facebook.com" in page.url
                logger.info(f"Estado sesion: {'LOGUEADO' if logged_in else 'SIN SESION — cierra Chrome e intentalo de nuevo'}")
            else:
                logged_in = await facebook_login(page, mobile=False)
            await asyncio.sleep(1.0)

            sections = [(config.PAGE_URL, "post")]

            # ── Fase 1: Recolectar URLs ──────────────────────────────
            logger.info("\nFASE 1: Recolectando URLs de publicaciones...\n")
            all_post_urls = []
            for section_url, post_type in sections:
                urls = await collect_post_urls(page, section_url, post_type, already_scraped)
                all_post_urls.extend(urls)
                await human_delay(3, 5)

            total = len(all_post_urls)
            logger.info(f"\nTotal posts a procesar: {total}\n")

            if not total:
                logger.warning("No se encontraron URLs. Asegurate de tener sesion de Facebook activa.")
                return

            # ── Fase 2: Procesar cada post ───────────────────────────
            logger.info("FASE 2: Extrayendo datos + comentarios (GraphQL)...\n")
            posts_since_rotation = 0

            for i, (post_url, post_type) in enumerate(all_post_urls, 1):
                if post_url in already_scraped:
                    logger.info(f"[{i}/{total}] Saltando (ya existe) -> {post_url}")
                    continue
                logger.info(f"\n[{i}/{total}] {post_type.upper()} -> {post_url}")

                # Rotar proxy si corresponde
                posts_since_rotation += 1
                if config.USE_PROXY and posts_since_rotation >= config.PROXY_ROTATION_EVERY:
                    proxy = proxy_rotator.get_next()
                    if proxy:
                        logger.info("Rotando proxy...")
                        await context.close()
                        if browser:
                            await browser.close()
                        browser, context = await create_browser(pw, proxy, mobile=True)
                        page = await context.new_page()
                        if logged_in and not config.USE_CHROME_SESSION:
                            await facebook_login(page, mobile=False)
                    posts_since_rotation = 0

                success = await process_post(page, post_url, post_type)
                if not success:
                    logger.warning(f"  No se pudo procesar: {post_url}")

                await human_delay()

            # ── Resumen final ─────────────────────────────────────────
            stats_end = get_stats()
            print("\n" + "="*60)
            print("  SCRAPING COMPLETADO")
            print(f"  Posts nuevos       : {stats_end['posts'] - stats_start['posts']}")
            print(f"  Comentarios nuevos : {stats_end['comments'] - stats_start['comments']}")
            print(f"  Total posts        : {stats_end['posts']}")
            print(f"  Total comentarios  : {stats_end['comments']}")
            print(f"\n  Archivos:")
            print(f"  output/posts_summary.csv")
            print(f"  output/comments.csv")
            print("="*60 + "\n")

        except KeyboardInterrupt:
            logger.info("\nInterrumpido. Datos guardados en output/")
        except Exception as e:
            logger.error(f"Error critico: {e}", exc_info=True)
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(run_scraper())
