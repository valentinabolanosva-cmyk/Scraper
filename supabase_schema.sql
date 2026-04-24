-- ============================================================
--  SCHEMA SUPABASE — Scrapear / La Polémica Del Huila
--  Alineado con los CSVs generados por el pipeline.
-- ============================================================

-- 1. Extensión UUID (por si se usa en el futuro)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- 2. POSTS  ← corresponde a output/posts_summary.csv
-- ============================================================
CREATE TABLE IF NOT EXISTS public.posts (
    post_url          TEXT PRIMARY KEY,
    post_date         TEXT,
    post_type         TEXT,
    post_text         TEXT,
    total_likes       INTEGER DEFAULT 0,
    total_comments    INTEGER DEFAULT 0,
    total_shares      INTEGER DEFAULT 0,
    total_views       INTEGER DEFAULT 0,
    comments_scraped  INTEGER DEFAULT 0,
    scraped_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 3. COMMENTS  ← corresponde a output/comments_analizados.csv
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comments (
    id               BIGSERIAL PRIMARY KEY,
    post_url         TEXT NOT NULL,
    post_date        TEXT,
    post_type        TEXT,
    comment_order    INTEGER,
    commenter_name   TEXT,
    comment_text     TEXT,
    comment_likes    INTEGER DEFAULT 0,
    comment_date     TEXT,
    is_reply         BOOLEAN DEFAULT FALSE,
    scraped_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    temperatura      DECIMAL(3, 2),
    tipo_humor       TEXT,
    justificacion    TEXT,
    sentimiento      TEXT,
    UNIQUE (post_url, comment_order)
);

CREATE INDEX IF NOT EXISTS idx_comments_post_url    ON public.comments (post_url);
CREATE INDEX IF NOT EXISTS idx_comments_sentimiento ON public.comments (sentimiento);


-- ============================================================
-- 4. ANALISIS_COMENTARIOS  ← usada por /analizar/ (API en vivo)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.analisis_comentarios (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    comentario_original      TEXT NOT NULL,
    calificacion_temperatura DECIMAL(3, 2) NOT NULL,
    tipo_humor               TEXT NOT NULL,
    justificacion            TEXT NOT NULL,
    created_at               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 5. RLS (Row-Level Security) — acceso anónimo controlado
-- ============================================================
ALTER TABLE public.posts                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comments              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analisis_comentarios  ENABLE ROW LEVEL SECURITY;

-- Lectura anónima (dashboard público)
DROP POLICY IF EXISTS "read posts anon"    ON public.posts;
CREATE POLICY "read posts anon"    ON public.posts                 FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "read comments anon" ON public.comments;
CREATE POLICY "read comments anon" ON public.comments              FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "read analisis anon" ON public.analisis_comentarios;
CREATE POLICY "read analisis anon" ON public.analisis_comentarios  FOR SELECT TO anon USING (true);

-- Inserciones anónimas SOLO para analisis_comentarios (usado por el endpoint /analizar/)
DROP POLICY IF EXISTS "insert analisis anon" ON public.analisis_comentarios;
CREATE POLICY "insert analisis anon" ON public.analisis_comentarios FOR INSERT TO anon WITH CHECK (true);

-- Las tablas posts/comments se pueblan desde subir_supabase.py con service_role,
-- que bypassa RLS. NO se crean políticas de INSERT anónimas para evitar spam.
