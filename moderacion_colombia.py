import re


AGRESIVO_TERMS = {
    "tonto", "tonta", "puta", "puta", "hp", "hpta", "hijueputa", "gonorrea",
    "malparido", "malparida", "inservible", "basura", "estorbo", "rata",
    "ladron", "ladrón", "idiota", "imbecil", "imbécil", "estupido", "estúpido",
    "porqueria", "porquería", "mierda", "payaso", "ridiculo", "ridículo",
}

POSITIVO_TERMS = {
    "excelente", "excelentes", "felicidades", "felicitaciones", "gracias",
    "teso", "tesos", "chimba", "bacano", "bacana", "genial", "crack",
    "apoyo", "duro", "duros", "berraco", "berracos",
}

PREGUNTA_TERMS = {
    "como", "cómo", "cuando", "cuándo", "donde", "dónde", "quien", "quién",
    "por que", "por qué", "que", "qué", "cual", "cuál",
}

# --- REGLAS AVANZADAS DE SARCASMO COLOMBIANO ---

# SARCASMO NEGATIVO: Queja, impunidad y cinismo
SARCASMO_NEGATIVO_PATTERNS = [
    # Preguntas retóricas de impunidad
    r"quien responde", r"quién responde", r"donde esta la plata", r"dónde está la plata", r"quien vigila", r"quién vigila",
    # Falsa sorpresa / Falso alivio
    r"tan raro", r"qué belleza", r"que belleza", r"menos mal que", r"faltaba más", r"faltaba mas",
    # El falso imperativo (Sarcasmo de castigo)
    r"sigan votando", r"sigan creyendo", r"eso, aplaudan", r"eso aplaudan", r"ahi tienen su cambio", r"ahí tienen su cambio",
    # Aceptación de la desgracia
    r"así es este platanal", r"asi es este platanal", r"cosas que solo pasan en locombia", r"cosas que solo pasan en colombia"
]

# SARCASMO POSITIVO: Elogio encubierto o acuerdo a regañadientes
SARCASMO_POSITIVO_PATTERNS = [
    # Concesión a regañadientes
    r"fastidio darle la razón", r"fastidio darle la razon", r"me cae pésimo", r"me cae pesimo", 
    r"toda la vida dándole palo", r"toda la vida dandole palo", r"toca aplaudirlo", r"toca aplaudirla",
    r"tener que admitirlo", r"desgracia tener que", r"habló con la verdad", r"hablo con la verdad",
    # Insulto admirativo
    r"es el diablo para hablar", r"mucha rata como juega", r"mucha rata cómo juega", r"mucha rata como hace", r"mucha rata cómo hace"
]

NEGATIVE_POLITICAL_MULTIWORD = {
    "promete y no cumple",
    "prometen y no cumplen",
    "prometio y no cumplio",
    "prometió y no cumplió",
    "seguiran perdiendo",
    "seguirán perdiendo",
    "no van a ganar nada",
    "se van a quemar",
    "se va a quemar",
    "que se siente este",
    "qué se siente este",
    "que se cree este",
    "qué se cree este",
}

NEGATIVE_POLITICAL_SINGLE = {
    "maquinaria", "maquinarias", "mermelada", "puestos",
    "clientelismo", "corrupto", "corrupta", "corruptos", "corruptas",
    "mentiroso", "mentirosa", "deshonesto", "deshonesta",
    "incumple", "incumplen", "engaño", "engano", "rechazo",
    "quemar", "quemados", "perdiendo",
}


def _normalize(text: str) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    normalized = text.strip().lower()
    if normalized in {"nan", "none"}:
        return ""
    return re.sub(r"\s+", " ", normalized)


def _tokenize(text: str):
    return re.findall(r"\w+", text, flags=re.UNICODE)


def _find_term(text: str, token_set: set, terms: set):
    for term in terms:
        if " " in term:
            if term in text:
                return term
        elif term in token_set:
            return term
    return None


def analizar_comentario_colombia(texto: str) -> dict:
    t = _normalize(texto)
    if not t:
        return {
            "categoria": "NEUTRO",
            "temperatura": 0.30,
            "tipo_humor": "Neutro / Informativo",
            "justificacion": "Texto vacío o sin contenido evaluable.",
            "palabra_clave": None,
            "sentimiento_dashboard": "Neutral",
        }

    # 1. FILTRO DE SARCASMO E IRONÍA COLOMBIANA (INSTRUCCIÓN AVANZADA)
    
    # Check for Positive Sarcasm first (grudging respect)
    for pattern in SARCASMO_POSITIVO_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return {
                "categoria": "POSITIVO",
                "temperatura": 0.15,
                "tipo_humor": "Sarcasmo Positivo / Admiración",
                "justificacion": f"Detectado sarcasmo positivo ('{pattern}'): Concesión a regañadientes o insulto admirativo.",
                "palabra_clave": pattern,
                "sentimiento_dashboard": "Positivo",
            }

    # Check for Negative Sarcasm (Indignation, False praise, etc.)
    for pattern in SARCASMO_NEGATIVO_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return {
                "categoria": "AGRESIVO",
                "temperatura": 0.88,
                "tipo_humor": "Sarcasmo Negativo / Ironía",
                "justificacion": f"Detectado sarcasmo negativo ('{pattern}'): Pregunta de impunidad, falso halago o resignación cínica.",
                "palabra_clave": pattern,
                "sentimiento_dashboard": "Negativo",
            }

    token_set = set(_tokenize(t))

    agresivo = _find_term(t, token_set, AGRESIVO_TERMS)
    if agresivo:
        return {
            "categoria": "AGRESIVO",
            "temperatura": 0.92,
            "tipo_humor": "Muy Agresivo / Troll",
            "justificacion": "Contiene ataque, insulto o denigración directa.",
            "palabra_clave": agresivo,
            "sentimiento_dashboard": "Negativo",
        }

    # Regla Colombia: negatividad política implícita aunque no haya groserías.
    neg_phrase = _find_term(t, token_set, NEGATIVE_POLITICAL_MULTIWORD)
    neg_term = _find_term(t, token_set, NEGATIVE_POLITICAL_SINGLE)
    rhetorical_indignation = ("este que?" in t) or ("este qué?" in t)
    promise_and_job_pattern = (
        ("promet" in t and ("cumpl" in t or "incumpl" in t))
        and any(w in token_set for w in {"trabajo", "empleo", "ayudas", "puestos"})
    )

    if neg_phrase or neg_term or rhetorical_indignation or promise_and_job_pattern:
        key = neg_phrase or neg_term or ("este qué?" if rhetorical_indignation else "promesa incumplida")
        return {
            "categoria": "AGRESIVO",
            "temperatura": 0.78,
            "tipo_humor": "Negativo / Sarcástico",
            "justificacion": "Expresa desconfianza, indignación o rechazo político en clave colombiana.",
            "palabra_clave": key,
            "sentimiento_dashboard": "Negativo",
        }

    positivo = _find_term(t, token_set, POSITIVO_TERMS)
    if positivo:
        return {
            "categoria": "POSITIVO",
            "temperatura": 0.10,
            "tipo_humor": "Positivo / Directo",
            "justificacion": "Contiene elogio, apoyo o aprobación explícita.",
            "palabra_clave": positivo,
            "sentimiento_dashboard": "Positivo",
        }

    tiene_pregunta = ("?" in t) or ("¿" in t) or (_find_term(t, token_set, PREGUNTA_TERMS) is not None)
    if tiene_pregunta:
        return {
            "categoria": "NEUTRO",
            "temperatura": 0.40,
            "tipo_humor": "Neutro / Informativo",
            "justificacion": "Es pregunta o petición de información sin agresión.",
            "palabra_clave": "?",
            "sentimiento_dashboard": "Neutral",
        }

    return {
        "categoria": "NEUTRO",
        "temperatura": 0.35,
        "tipo_humor": "Neutro / Informativo",
        "justificacion": "Comentario de opinión sin ataque ni elogio marcado.",
        "palabra_clave": None,
        "sentimiento_dashboard": "Neutral",
    }

