"""
LinkedIn Jobs Guest API scraper.

Uses LinkedIn's public (no-auth) Guest API to scrape job postings.
Based on https://github.com/hendrixfreire/linkedin-job-scraper

No API keys needed — uses LinkedIn's public HTML endpoints.
Stdlib only, no external dependencies for scraping.
"""
import os
import re
import sys
import html
import json
import time
import firebase_admin
from firebase_admin import credentials, firestore
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# --- CREDENCIALES (desde variables de entorno) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIREBASE_JSON_STR = os.environ.get("FIREBASE_CREDENTIALS")

# --- INICIALIZACIÓN FIREBASE ---
if FIREBASE_JSON_STR:
    try:
        cred_dict = json.loads(FIREBASE_JSON_STR)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print(f"❌ Error al inicializar Firebase: {e}")
        exit()
else:
    print("❌ Error: No se encontró FIREBASE_CREDENTIALS")
    exit()


# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE BÚSQUEDA
# ═══════════════════════════════════════════════════════════════

# --- URLs de la API Guest de LinkedIn ---
BASE_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
BASE_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"

# --- FILTROS API ---
# f_TPR: tiempo de publicación (r86400=24h, r604800=semana, r2592000=mes)
# f_E: nivel experiencia (1=Intern, 2=Entry, 3=Associate, 4=Mid-Senior,
#       5=Director, 6=Executive)
# f_WT: tipo trabajo (1=Presencial, 2=Remoto, 3=Híbrido)
# sortBy=DD: ordenar por fecha descendente (más recientes primero)

# --- KEYWORDS ---
# Tus términos de búsqueda actuales, adaptados al formato Guest API.
# Cada keyword genera 2 queries: Remoto España + Madrid (sin filtro de modalidad)
KEYWORDS = [
    "pentester",
    "'red team'",
    "'blue team'",
    "'hacking ético'",
    "ciberseguridad",
    "cybersecurity",
    "'cyber security'",
    "'seguridad informática'",
    "devsecops",
    "'penetration tester'",
    "SOC",
    "'SOC Analyst'",
    "'Security Analyst'",
    "'Threat Monitoring'",
    # --- Administrador de Sistemas ---
    "'administrador de sistemas'",
    "'administración de sistemas'",
    "sysadmin",
    "'system administrator'",
    "systems engineer",
    "sistemas linux",
    # --- Inteligencia Artificial ---
    "IA",
    "AI",
    "'inteligencia artificial'",
    "'artificial intelligence'",
    "machine learning",
    "mlops",
    "genai"
]

# --- ZONAS MADRID (para presencial o híbrido) ---
ZONAS_MADRID = [
    "madrid", "alcobendas", "pozuelo", "las rozas", 
    "getafe", "leganés", "móstoles", "fuenlabrada",
    "boadilla", "majadahonda", "tres cantos", "alcorcón",
    "san sebastián de los reyes", "ss de los reyes", "parla",
    "valdemoro", "pinto", "alcalá", "torrejón"
]

# --- PALABRAS PROHIBIDAS EN TÍTULO (filtro senioridad) ---
PALABRAS_PROHIBIDAS = [
    "senior", "sr", "lead", "principal", "manager",
    "director", "architect", "arquitecto", "expert",
    "head", "chief", "cpo", "cto", "ceo", "cfo", "vp", "vice", "president"
]

# --- KEYWORDS DE FLEXIBILIDAD ---
KEYWORDS_FLEXIBILIDAD = [
    "remoto", "remote", "híbrido", "hibrido",
    "hybrid", "teletrabajo",
]

# --- HTTP HEADERS ---
# User-Agent de Chrome para evitar ser bloqueado como bot
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
}


# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def trabajo_ya_existe(job_id):
    doc_ref = db.collection("ofertas_enviadas").document(job_id)
    return doc_ref.get().exists


def guardar_trabajo(job_id, oferta):
    db.collection("ofertas_enviadas").document(job_id).set({
        "titulo": oferta["titulo"],
        "empresa": oferta["empresa"],
        "fecha_registro": firestore.SERVER_TIMESTAMP
    })


# ═══════════════════════════════════════════════════════════════
# SCRAPER — GUEST API DE LINKEDIN
# ═══════════════════════════════════════════════════════════════

def fetch_url(url, retries=3):
    """HTTP request con retry y rate limiting.

    Usa urllib.request (stdlib) — no necesita requests ni http.client.
    Timeout de 8s por petición. Retry con backoff para evitar 429.
    """
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=8) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt < retries:
                # Si nos bloquean por muchas peticiones (429), esperamos más
                if hasattr(e, 'code') and e.code == 429:
                    espera = 5 + (attempt * 5)
                    print(f"⚠️ 429 Too Many Requests. Esperando {espera}s...", file=sys.stderr)
                    time.sleep(espera)
                else:
                    time.sleep(2)
            else:
                print(f"Error fetching {url}: {e}", file=sys.stderr)
                return ""


def parse_search_results(search_html):
    """Extrae ofertas del HTML de búsqueda de la Guest API usando regex.

    El HTML de la Guest API tiene estructura conocida:
    <li data-entity-urn="urn:li:jobPosting:123456"> ... </li>

    Cada tarjeta contiene: título, empresa, ubicación, fecha.
    """
    jobs = []
    seen_ids = set()  # dedup intra-página

    # Cada <li> con data-entity-urn es una tarjeta de oferta
    card_pattern = re.compile(
        r'data-entity-urn="urn:li:jobPosting:(\d+)"(.*?)</li>',
        re.DOTALL
    )

    for match in card_pattern.finditer(search_html):
        job_id = match.group(1)        # ID numérico de la oferta
        card_html = match.group(2)     # HTML interno de la tarjeta

        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Título: dentro de h3 con clase base-search-card__title
        title_match = re.search(
            r'base-search-card__title[^>]*>\s*(.*?)\s*</h3>',
            card_html, re.DOTALL
        )
        title = title_match.group(1).strip() if title_match else ""
        title = re.sub(r'<[^>]+>', '', title).strip()

        # Empresa: primero hidden-nested-link (más común),
        # fallback: base-search-card__subtitle
        company_match = re.search(
            r'hidden-nested-link[^>]*>\s*(.*?)\s*</a>',
            card_html, re.DOTALL
        )
        if not company_match:
            company_match = re.search(
                r'base-search-card__subtitle[^>]*>(.*?)</h4>',
                card_html, re.DOTALL
            )
        company = company_match.group(1).strip() if company_match else ""
        company = re.sub(r'<[^>]+>', '', company).strip()

        # Ubicación: span con clase job-search-card__location
        location_match = re.search(
            r'job-search-card__location[^>]*>\s*(.*?)\s*</span>',
            card_html, re.DOTALL
        )
        location = location_match.group(1).strip() if location_match else ""

        # Fecha: etiqueta <time> con atributo datetime (ISO) y texto relativo
        date_match = re.search(
            r'<time[^>]*datetime="([^"]*)"[^>]*>(.*?)</time>',
            card_html, re.DOTALL
        )
        date_label = re.sub(r'<[^>]+>', '', date_match.group(2)).strip() if date_match else ""

        jobs.append({
            "id": job_id,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "title": title,
            "company": company,
            "location": location,
            "date_label": date_label,
        })

    return jobs


def search_jobs(params, max_pages=2):
    """Busca ofertas vía Guest API con paginación.

    Cada página devuelve hasta 25 ofertas. El parámetro 'start'
    controla el offset (0, 25, 50, ...). Si una página no devuelve
    resultados nuevos, la paginación se detiene.
    """
    all_jobs = []
    seen_ids = set()  # dedup entre páginas

    for page in range(max_pages):
        start = page * 25
        p = {**params, "start": start}
        url = f"{BASE_SEARCH_URL}?{urlencode(p)}"
        search_html = fetch_url(url)
        if not search_html:
            break

        jobs = parse_search_results(search_html)
        new_count = 0
        for job in jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                all_jobs.append(job)
                new_count += 1

        if new_count == 0:  # página sin resultados nuevos → fin
            break
        time.sleep(3)     # rate limiting: 3s entre páginas para evitar 429

    return all_jobs


def get_job_details(job_id):
    """Obtiene detalles de una oferta específica vía la API de detalle.

    Hace fetch de la página individual de la oferta, limpia el HTML
    y extrae:
    - work_mode: Remote/Hybrid/On-site
    - description: primeros 500 chars tras marcadores conocidos
    - closed: True si ya no acepta solicitudes
    """
    url = BASE_JOB_URL.format(job_id)
    detail_html = fetch_url(url)
    if not detail_html:
        return {}

    # Limpiar HTML: reemplazar tags con espacios y colapsar whitespace
    text = re.sub(r'<[^>]+>', ' ', detail_html)
    text = re.sub(r'\s+', ' ', text).strip()

    details = {}

    # Extraer modo de trabajo
    for pattern in [r'(Remote|Remoto|Hybrid|Híbrido|On-site|Presencial)']:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details["work_mode"] = match.group(1)
            break

    # Extraer descripción — buscar marcadores y coger hasta 500 chars
    for marker in ["Job description", "Descripción del puesto", "About the job", "Responsibilities"]:
        idx = text.lower().find(marker.lower())
        if idx > 0:
            desc = text[idx:idx+800]
            details["description"] = desc.strip()[:500]
            break

    # Comprobar si la oferta está cerrada
    if "no longer accepting applications" in text.lower() or "ya no acepta" in text.lower():
        details["closed"] = True

    return details


def build_searches(keywords):
    """Construye queries de búsqueda a partir de la lista de keywords.

    Cada keyword genera 2 queries:
    1. Remoto en España (f_WT=2 para remoto)
    2. Madrid sin filtro de modalidad (devuelve remoto+híbrido+presencial)
    """
    searches = []

    # Remoto en España
    for kw in keywords:
        searches.append({
            "keywords": kw,
            "location": "Spain",
            "f_WT": "2",           # Solo remoto
            "f_TPR": "r86400",     # Últimas 24h
            "sortBy": "DD",        # Más recientes primero
        })

    # Madrid (todas las modalidades)
    for kw in keywords:
        searches.append({
            "keywords": kw,
            "location": "Madrid, Spain",
            "f_TPR": "r86400",
            "sortBy": "DD",
        })

    return searches


# ═══════════════════════════════════════════════════════════════
# 1. BÚSQUEDA (Guest API)
# ═══════════════════════════════════════════════════════════════

def buscar_trabajos(on_job_found=None):
    """Pipeline completo de búsqueda en la Guest API de LinkedIn."""
    ofertas_totales = []
    searches = build_searches(KEYWORDS)
    all_seen_ids = set()  # dedup entre queries

    print(f"🔍 Buscando en LinkedIn Guest API — {len(KEYWORDS)} keywords × 2 queries = {len(searches)} búsquedas")
    print(f"⏱️ Bucle continuo: Paginación: 2 páginas × 25 ofertas por query")

    for params in searches:
        jobs = search_jobs(params, max_pages=2)
        kw = params.get("keywords", "")

        for job in jobs:
            if job["id"] not in all_seen_ids:
                all_seen_ids.add(job["id"])

                # Obtener detalles (descripción, modo trabajo)
                details = get_job_details(job["id"])
                time.sleep(2)  # rate limiting: 2s entre llamadas de detalle

                # Saltar ofertas cerradas
                if details.get("closed"):
                    print(f"⏭️ Oferta cerrada: {job['title']}", file=sys.stderr)
                    continue

                # Determinar si es remoto
                work_mode = details.get("work_mode", "")
                es_remoto = work_mode.lower() in ("remote", "remoto")

                oferta = {
                    "id": str(job["id"]),
                    "titulo": job.get("title", ""),
                    "empresa": job.get("company", "Empresa oculta"),
                    "ubicacion": job.get("location", ""),
                    "descripcion": details.get("description", ""),
                    "enlace": job.get("url", ""),
                    "plataforma": "LinkedIn",
                    "es_remoto": es_remoto,
                    "work_mode": work_mode,
                }
                ofertas_totales.append(oferta)
                
                if on_job_found:
                    on_job_found(oferta)

        time.sleep(5)  # delay de 5s entre keywords para proteger la IP

    print(f"📦 LinkedIn Guest API: {len(ofertas_totales)} ofertas encontradas en total en este ciclo.")
    return ofertas_totales


# ═══════════════════════════════════════════════════════════════
# 2. FILTRADO
# ═══════════════════════════════════════════════════════════════

def filtrar_ofertas(ofertas):
    """Filtra ofertas por senioridad, zona y modalidad.

    - Excluye senior/lead/manager/director/architect. Incluye junior.
    - Zona: Madrid y alrededores si es presencial o híbrido.
    - Cualquier lugar de España si es teletrabajo (remoto).
    """
    ofertas_validas = []

    for oferta in ofertas:
        titulo_low = oferta["titulo"].lower()
        ubicacion_low = oferta["ubicacion"].lower()
        descripcion_low = oferta.get("descripcion", "").lower()

        # Excluir por senioridad (excluimos senior, lead, manager, head, etc.)
        es_senior = any(word in titulo_low.split() for word in PALABRAS_PROHIBIDAS)
        if es_senior:
            print(f"❌ Rechazada (Senioridad): {oferta['titulo']}")
            continue

        # Validar que realmente contenga alguna de las palabras clave de búsqueda
        # (quitamos las comillas simples que usamos para la API de LinkedIn)
        keywords_limpias = [kw.replace("'", "").lower() for kw in KEYWORDS]
        # Añadimos palabras comodín que queremos aceptar pero por las que no queremos buscar en LinkedIn (para evitar guardias de seguridad físicos)
        keywords_limpias.extend(["security", "seguridad"])
        
        tiene_keyword = False
        for kw in keywords_limpias:
            # Usamos \b para que coincida con la palabra completa y no como parte de otra (ej: "ia" dentro de "oficial")
            patron = r'\b' + re.escape(kw) + r'\b'
            if re.search(patron, titulo_low) or re.search(patron, descripcion_low):
                tiene_keyword = True
                break
                
        if not tiene_keyword:
            print(f"❌ Rechazada (Sin keyword exacta): {oferta['titulo']}")
            continue

        # Determinar si es remoto (teletrabajo)
        es_remoto = oferta.get("es_remoto", False)
        work_mode = oferta.get("work_mode", "").lower()
        
        if work_mode in ("remote", "remoto"):
            es_remoto = True
        if any(kw in titulo_low or kw in descripcion_low or kw in ubicacion_low for kw in KEYWORDS_FLEXIBILIDAD):
            es_remoto = True

        es_hibrido = work_mode in ("hybrid", "híbrido") or "híbrido" in titulo_low or "hybrid" in titulo_low or "híbrido" in descripcion_low or "hybrid" in descripcion_low
        
        # Filtros de ubicación:
        # - Si es remoto: Cualquier lugar de España (asumimos que todo lo que devuelve es de España por las queries)
        # - Si es presencial o híbrido: Solo zonas de Madrid
        en_madrid = any(ciudad in ubicacion_low for ciudad in ZONAS_MADRID)

        if es_remoto:
            oferta["modalidad"] = "🏠 Remoto / Teletrabajo"
            if oferta["enlace"]:
                ofertas_validas.append(oferta)
            else:
                print(f"❌ Rechazada (Sin enlace): {oferta['titulo']}")
        elif en_madrid:
            if es_hibrido:
                oferta["modalidad"] = "🏠🏢 Híbrido"
            else:
                oferta["modalidad"] = "🏢 Presencial"
            if oferta["enlace"]:
                ofertas_validas.append(oferta)
            else:
                print(f"❌ Rechazada (Sin enlace): {oferta['titulo']}")
        else:
            print(f"❌ Rechazada (Ubicación/Modalidad): {oferta['titulo']} - {oferta.get('ubicacion', '')} ({work_mode})")

    return ofertas_validas


# ═══════════════════════════════════════════════════════════════
# 3. ENVÍO A TELEGRAM
# ═══════════════════════════════════════════════════════════════

def enviar_oferta_telegram(oferta):
    import requests  # Importado localmente

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    texto = f"🚨 <b>Nueva Oferta (LinkedIn):</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🛠️ <b>Modalidad:</b> {oferta['modalidad']}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{html.escape(oferta['enlace'])}'>Haz clic aquí para aplicar</a>"

    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🔗 Ver Oferta", "url": oferta['enlace']}],
                [
                    {"text": "✅ Aceptar", "callback_data": "aceptar"},
                    {"text": "❌ Rechazar", "callback_data": "rechazar"}
                ]
            ]
        }
    }

    try:
        r = requests.post(url, json=payload)

        # Manejo de Rate Limit de Telegram (429)
        if r.status_code == 429:
            try:
                error_data = r.json()
                retry_after = error_data.get("parameters", {}).get("retry_after", 30)
            except Exception:
                retry_after = 30
            print(f"⚠️ Rate Limit de Telegram. Esperando {retry_after} segundos...")
            time.sleep(retry_after)
            r = requests.post(url, json=payload)  # Reintento

        if r.status_code != 200:
            print(f"❌ Error Telegram ({r.status_code}): {r.text}")
            return False

        return True
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# EJECUCIÓN
# ═══════════════════════════════════════════════════════════════

def main_loop():
    while True:
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando ciclo de búsqueda...")
            estadisticas = {"nuevas": 0, "duplicadas": 0, "filtradas_out": 0}

            def procesar_oferta(job):
                # 1. Aplicar los filtros a esta oferta individual
                filtradas = filtrar_ofertas([job])
                if not filtradas:
                    estadisticas["filtradas_out"] += 1
                    return
                
                # 2. Si pasa los filtros, comprobar BD y enviar a Telegram
                job_id = job["id"]
                if job_id and not trabajo_ya_existe(job_id):
                    exito = enviar_oferta_telegram(job)
                    if exito:
                        guardar_trabajo(job_id, job)
                        print(f"📩 ENVIADA AL INSTANTE: {job['titulo']} en {job['empresa']}")
                        estadisticas["nuevas"] += 1
                    else:
                        print(f"⚠️ Fallo al enviar a Telegram: {job['titulo']}")
                elif job_id:
                    estadisticas["duplicadas"] += 1

            # Llamamos a buscar_trabajos y le pasamos la función para que las envíe sobre la marcha
            buscar_trabajos(on_job_found=procesar_oferta)

            print(f"\n📊 Resumen del ciclo: {estadisticas['nuevas']} nuevas enviadas | {estadisticas['duplicadas']} ya en BD | {estadisticas['filtradas_out']} descartadas por filtros")
        except Exception as e:
            print(f"❌ Error en el ciclo principal: {e}", file=sys.stderr)
        
        print("🔄 Reiniciando el ciclo de búsqueda de inmediato...\n")
        time.sleep(2)


if __name__ == "__main__":
    main_loop()
