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

# --- 1. BÚSQUEDA (5 PÁGINAS / ÚLTIMA SEMANA) ---
def buscar_trabajos():
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    
    ofertas_totales = []
    max_paginas = 5 # Barrido profundo inicial

    print("🔎 Iniciando búsqueda de la SEMANA (5 páginas)...")

    for pagina in range(1, max_paginas + 1):
        params = {
            "query": 'pentester OR "red team" OR "blue team" OR hacking OR ciberseguridad OR cybersecurity OR penetration in Madrid, Spain',
            "page": str(pagina),
            "num_pages": "1",
            "date_posted": "week", # <--- Mantengo "week" para el barrido inicial
            "country": "es",
            "radius": "50"
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if not data:
                    print(f"✅ No hay más resultados en la página {pagina}.")
                    break
                
                print(f"📦 Página {pagina}: {len(data)} ofertas encontradas.")
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
                print(f"❌ Error API pág {pagina}: {response.status_code}")
                break
        except Exception as e:
            print(f"❌ Error en petición: {e}")
            break
            
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
    
    texto = f"🚨 <b>Nueva Vacante:</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🛠️ <b>Modalidad:</b> {oferta['modalidad']}\n"
    texto += f"🌐 <b>Vía:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{html.escape(oferta['enlace'])}'>¡Aplicar ya!</a>"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error Telegram: {e}")

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
