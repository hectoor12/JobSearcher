import os
import requests
import html
import json
import firebase_admin
from firebase_admin import credentials, firestore

# --- CREDENCIALES ---
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") # Tu clave de RapidAPI
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIREBASE_JSON_STR = os.environ.get("FIREBASE_CREDENTIALS")

# --- INICIALIZACIÓN FIREBASE ---
if FIREBASE_JSON_STR:
    try:
        cred_dict = json.loads(FIREBASE_JSON_STR)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print(f"Error al inicializar Firebase: {e}")
        exit()
else:
    print("Error: No se encontró la variable FIREBASE_CREDENTIALS")
    exit()

# --- FUNCIONES DE BASE DE DATOS ---
def trabajo_ya_existe(job_id):
    """Consulta si el ID de JSearch ya existe en Firestore."""
    doc_ref = db.collection("ofertas_enviadas").document(job_id)
    return doc_ref.get().exists

def guardar_trabajo(job_id, oferta):
    """Registra el trabajo para no volver a enviarlo."""
    db.collection("ofertas_enviadas").document(job_id).set({
        "titulo": oferta["titulo"],
        "empresa": oferta["empresa"],
        "fecha_registro": firestore.SERVER_TIMESTAMP
    })

# --- 1. BÚSQUEDA CON JSEARCH ---
def buscar_trabajos():
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    
    ofertas_totales = []
    # Parámetros según tu petición anterior
    params = {
        "query": "developer jobs in chicago",
        "page": "1",
        "num_pages": "1",
        "date_posted": "all",
        "country": "us"
    }

    print(f"🔎 Buscando en JSearch: {params['query']}...")

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get("data", [])
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
        print(f"❌ Error en la petición: {e}")
        
    print(f"📊 Ofertas encontradas: {len(ofertas_totales)}")
    return ofertas_totales

# --- 2. FILTRADO ---
def filtrar_ofertas(ofertas):
    ofertas_validas = []
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect"]

    for oferta in ofertas:
        titulo = oferta["titulo"].lower()
        
        # Filtro Seniority
        es_senior = any(word in titulo.split() for word in palabras_prohibidas)
        
        if not es_senior and oferta["enlace"]:
            # Determinamos modalidad
            if oferta["es_remoto"]:
                oferta["modalidad"] = "🏠 Remoto"
            else:
                oferta["modalidad"] = "🏢 Presencial / Híbrido"
                
            ofertas_validas.append(oferta)
            
    return ofertas_validas

# --- 3. ENVÍO A TELEGRAM ---
def enviar_oferta_telegram(oferta):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    texto = f"🚨 <b>Nueva Oferta JSearch:</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🛠️ <b>Modalidad:</b> {oferta['modalidad']}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{html.escape(oferta['enlace'])}'>Postular ahora</a>"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🚀 Ver Oferta", "url": oferta['enlace']}],
                [
                    {"text": "✅ Guardar", "callback_data": "aceptar"},
                    {"text": "❌ Ignorar", "callback_data": "rechazar"}
                ]
            ]
        }
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error Telegram: {e}")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    if RAPIDAPI_KEY and TELEGRAM_TOKEN and CHAT_ID:
        todas = buscar_trabajos()
        
        if todas:
            filtradas = filtrar_ofertas(todas)
            print(f"🎯 Tras filtros: {len(filtradas)}")
            
            for trabajo in filtradas:
                # Usamos el job_id real de la API
                job_id = trabajo["id"]
                
                if not trabajo_ya_existe(job_id):
                    enviar_oferta_telegram(trabajo)
                    guardar_trabajo(job_id, trabajo)
                    print(f"📩 Enviada: {trabajo['titulo']}")
                else:
                    print(f"⏭️ Omitida (repetida): {trabajo['titulo']}")
        else:
            print("No se encontraron resultados.")
    else:
        print("Error: Faltan variables de entorno (RAPIDAPI_KEY, TELEGRAM_TOKEN, etc.)")
