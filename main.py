import os
import requests
import serpapi
import html
import json
import hashlib
import firebase_admin
from firebase_admin import credentials, firestore

# --- CREDENCIALES ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
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
    print("Error: No se encontró la variable de entorno FIREBASE_CREDENTIALS")
    exit()

# --- FUNCIONES DE BASE DE DATOS ---
def generar_id_unico(oferta):
    """Crea un ID único basado en el título y la empresa para evitar duplicados."""
    cadena = f"{oferta['titulo']}{oferta['empresa']}".lower().strip()
    return hashlib.md5(cadena.encode()).hexdigest()

def trabajo_ya_existe(job_id):
    """Consulta si el ID ya existe en la colección de Firestore."""
    doc_ref = db.collection("ofertas_enviadas").document(job_id)
    return doc_ref.get().exists

def guardar_trabajo(job_id, oferta):
    """Registra el trabajo en la base de datos."""
    db.collection("ofertas_enviadas").document(job_id).set({
        "titulo": oferta["titulo"],
        "empresa": oferta["empresa"],
        "fecha_registro": firestore.SERVER_TIMESTAMP
    })

# --- 1. BÚSQUEDA (Con Paginación y sin Chips) ---
def buscar_trabajos():
    client = serpapi.Client(api_key=SERPAPI_KEY)
    ofertas_totales = []
    start_index = 0
    max_paginas = 10  # Límite de seguridad (100 ofertas aprox) para no quemar la API
    
    print("🔎 Iniciando búsqueda exhaustiva en Google Jobs...")

    while start_index < (max_paginas * 10):
        try:
            params = {
                "engine": "google_jobs",
                "q": 'pentester OR "red team" OR "blue team" OR hacking OR ciberseguridad OR cybersecurity OR penetration',
                "location": "Madrid, Spain",
                "gl": "es",
                "hl": "es",
                "start": start_index  # Paginación
            }
            
            results = client.search(params)
            jobs = results.get("jobs_results", [])
            
            if not jobs:
                print(f"✅ No hay más resultados en la posición {start_index}.")
                break
                
            print(f"📦 Obtenidas {len(jobs)} ofertas de la página {int(start_index/10) + 1}...")

            for j in jobs:
                link = j.get("source_link")
                if not link and j.get("apply_options"):
                    link = j.get("apply_options")[0].get("link")
                
                ofertas_totales.append({
                    "titulo": j.get("title", ""),
                    "empresa": j.get("company_name", "Empresa oculta"),
                    "ubicacion": j.get("location", ""),
                    "descripcion": j.get("description", ""),
                    "enlace": link,
                    "plataforma": j.get("via", "Google Jobs").replace("via ", "").replace("vía ", "")
                })
            
            # Incrementamos para la siguiente página
            start_index += 10
            
        except Exception as e:
            print(f"Error en SerpAPI en la posición {start_index}: {e}")
            break
            
    print(f"📊 Total de ofertas brutas encontradas: {len(ofertas_totales)}")
    return ofertas_totales

# --- 2. FILTRADO ---
def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect", "arquitecto", "expert"]
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    # Hemos ampliado un poco los criterios de zona para ser menos estrictos
    ciudades_permitidas = ["madrid", "españa", "spain", "alcobendas", "pozuelo", "las rozas", "getafe", "leganés", "móstoles", "fuenlabrada"]

    for oferta in ofertas:
        titulo = oferta["titulo"].lower()
        descripcion = oferta["descripcion"].lower()
        ubicacion = oferta["ubicacion"].lower()
        
        # Lógica de filtrado
        es_senior = any(word in titulo.split() for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        # Si NO es senior Y (está en Madrid o es Remoto/Híbrido)
        if not es_senior and (en_zona or es_flexible):
            if oferta["enlace"]:
                if es_flexible:
                    oferta["modalidad"] = "🏠 Remoto / Híbrido"
                else:
                    oferta["modalidad"] = "🏢 Presencial o No especificada"
                
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
    if SERPAPI_KEY and TELEGRAM_TOKEN and CHAT_ID:
        todas = buscar_trabajos()
        
        if todas:
            filtradas = filtrar_ofertas(todas)
            print(f"🎯 Ofertas tras aplicar filtros: {len(filtradas)}")
            
            for trabajo in filtradas:
                job_id = generar_id_unico(trabajo)
                
                if not trabajo_ya_existe(job_id):
                    enviar_oferta_telegram(trabajo)
                    guardar_trabajo(job_id, trabajo)
                    print(f"📩 Enviada: {trabajo['titulo']} en {trabajo['empresa']}")
                else:
                    # Opcional: print(f"Omitida (ya existe): {trabajo['titulo']}")
                    pass
        else:
            print("No se encontraron ofertas en la búsqueda.")
    else:
        print("Error: Faltan variables de entorno (SERPAPI_KEY, TELEGRAM_TOKEN o TELEGRAM_CHAT_ID)")
        
