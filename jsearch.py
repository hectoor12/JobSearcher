import os
import requests
import html
import json
import firebase_admin
from firebase_admin import credentials, firestore

# --- CREDENCIALES ---
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
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
        print(f"Error al inicializar Firebase: {e}")
        exit()
else:
    print("Error: No se encontró FIREBASE_CREDENTIALS")
    exit()

# --- FUNCIONES DE BASE DE DATOS ---
def trabajo_ya_existe(job_id):
    doc_ref = db.collection("ofertas_enviadas").document(job_id)
    return doc_ref.get().exists

def guardar_trabajo(job_id, oferta):
    db.collection("ofertas_enviadas").document(job_id).set({
        "titulo": oferta["titulo"],
        "empresa": oferta["empresa"],
        "fecha_registro": firestore.SERVER_TIMESTAMP
    })

# --- NUEVA FUNCIÓN SECUENCIAL ---
def obtener_siguiente_query(terminos):
    """Guarda y lee de Firebase el índice por el que vamos para ir en orden"""
    doc_ref = db.collection("configuracion_bot").document("estado_busqueda")
    doc = doc_ref.get()
    
    # Si existe el documento, sacamos el índice. Si no, empezamos en 0.
    if doc.exists:
        indice_actual = doc.to_dict().get("indice", 0)
    else:
        indice_actual = 0
        
    # El índice que usaremos en esta ejecución
    indice_a_usar = indice_actual
    
    # Calculamos el siguiente índice. El "% len(terminos)" hace que vuelva a 0 cuando llegue al final
    siguiente_indice = (indice_actual + 1) % len(terminos)
    
    # Guardamos el siguiente índice para la próxima vez que se ejecute el script
    doc_ref.set({"indice": siguiente_indice})
    
    return terminos[indice_a_usar], indice_a_usar + 1 # Devolvemos también el número para imprimirlo

# --- 1. BÚSQUEDA (PÁGINA 1: SECUENCIAL + SOLO HOY) ---
def buscar_trabajos():
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    
    ofertas_totales = []

    # 1. Tu lista fija de términos (7 elementos)
    terminos_busqueda = [
        'pentester OR "red team" Madrid',
        '"blue team" OR "vulnerability assessor" OR "analista de vulnerabilidades" Madrid',
        'hacking OR "hacking ético" OR "hacker ético" Madrid',
        'ciberseguridad OR cybersecurity OR "seguridad informática" Madrid',
        'penetration OR "offensive security" OR "seguridad ofensiva" Madrid',
        '"security consultant" OR "consultor de seguridad" OR "auditor de seguridad" Madrid',
        '"application security" OR "it security" Madrid'
    ]

    # 2. Elegimos el término en ESTRICTO ORDEN secuencial
    query_secuencial, numero_ronda = obtener_siguiente_query(terminos_busqueda)
    print(f"🔍 Búsqueda de esta ronda ({numero_ronda}/{len(terminos_busqueda)}): {query_secuencial}")

    params = {
        "query": query_secuencial,
        "num_pages": "1",
        "date_posted": "today", 
        "country": "es"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get("data", [])
            print(f"📦 Página 1: {len(data)} ofertas encontradas.")
            
            for j in data:
                ofertas_totales.append({
                    "id": j.get("job_id"),
                    "titulo": j.get("job_title", ""),
                    "empresa": j.get("employer_name", "Empresa oculta"),
                    "ubicacion": f"{j.get('job_city', '')}, {j.get('job_state', '')}",
                    "descripcion": j.get("job_description", ""),
                    "enlace": j.get("job_apply_link"),
                    "plataforma": j.get("job_publisher", "JSearch"),
                    "es_remoto": j.get("job_is_remote", False)
                })
        else:
            print(f"❌ Error API: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error en petición: {e}")
            
    return ofertas_totales

# --- 2. FILTRADO ---
def filtrar_ofertas(ofertas):
    ofertas_validas = []
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect"]

    for oferta in ofertas:
        titulo_low = oferta["titulo"].lower()
        es_senior = any(word in titulo_low.split() for word in palabras_prohibidas)
        
        if not es_senior and oferta["enlace"]:
            oferta["modalidad"] = "🏠 Remoto" if oferta["es_remoto"] else "🏢 Presencial / Híbrido"
            ofertas_validas.append(oferta)
            
    return ofertas_validas

# --- 3. ENVÍO A TELEGRAM ---
def enviar_oferta_telegram(oferta):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    texto = f"🚨 <b>Nueva Oferta:</b> {html.escape(oferta['titulo'])}\n"
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
        if r.status_code != 200:
            print(f"❌ Error Telegram ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    ofertas_crudas = buscar_trabajos()
    filtradas = filtrar_ofertas(ofertas_crudas)
    
    print(f"🎯 Total tras filtros: {len(filtradas)}")
    
    for job in filtradas:
        job_id = job["id"]
        if not trabajo_ya_existe(job_id):
            enviar_oferta_telegram(job)
            guardar_trabajo(job_id, job)
            print(f"📩 Enviada: {job['titulo']}")
