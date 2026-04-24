# Facebook Scraper — LaPolemicaDelHuila 🇨🇴

Extrae **todos los likes, comentarios, shares y vistas** de cada publicación del perfil de Facebook.

## 📋 Requisitos

- Python 3.10 o superior
- Windows / Mac / Linux

## 🚀 Instalación (1 sola vez)

Abre una terminal en esta carpeta y ejecuta:

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Instalar los navegadores de Playwright
python -m playwright install chromium
```

## ⚙️ Configuración

Edita el archivo `config.py`:

| Opción | Descripción |
|---|---|
| `FB_EMAIL` / `FB_PASSWORD` | *(Opcional pero recomendado)* Credenciales de una cuenta Facebook para scraping más profundo |
| `USE_PROXY` | `True` para activar proxies |
| `HEADLESS` | `False` = navegador visible (más seguro) |
| `SCRAPE_PHOTOS` | `True/False` para activar/desactivar sección |
| `SCRAPE_VIDEOS` | `True/False` |
| `MAX_POSTS` | `0` = todos los posts |

## ▶️ Ejecutar

```bash
python scraper.py
```

## 📂 Salida de datos

Los datos se guardan automáticamente en:

- `output/posts_data.csv` → Excel compatible
- `output/posts_data.json` → Formato JSON
- `output/logs/scraper.log` → Registro de ejecución

### Columnas del CSV

| Columna | Descripción |
|---|---|
| `post_url` | URL directa al post |
| `post_date` | Fecha de publicación |
| `post_type` | `photo` / `video` / `post` |
| `post_text` | Texto de la publicación |
| `likes` | Total de reacciones |
| `comments` | Número de comentarios |
| `shares` | Número de compartidos |
| `views` | Reproducciones (solo videos) |
| `scraped_at` | Cuándo se scrapeó |

## 🔄 Reanudar si se interrumpe

Si el scraper se corta (Ctrl+C, cierre de PC, etc.), simplemente **vuelve a ejecutarlo**. Automáticamente saltará las URLs ya scrapeadas y continuará desde donde quedó.

## ⚠️ Notas importantes

- Usa una cuenta **"burner"** de Facebook, no la personal
- El scraping puede tomar **varias horas** dependiendo de cuántos posts tenga la página
- Si aparece un CAPTCHA, el scraper con `HEADLESS=False` te permitirá resolverlo manualmente
