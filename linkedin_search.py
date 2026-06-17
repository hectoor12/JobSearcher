import os
import http.client
import html
import json
import urllib.parse
import firebase_admin
from firebase_admin import credentials, firestore

# --- CREDENCIALES (desde variables de entorno, igual que los demás scripts) ---
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

# --- 1. BÚSQUEDA (LinkedIn Job Search API - TODOS los términos en 1 sola llamada) ---
def buscar_trabajos():
    ofertas_totales = []

    # Todos los términos combinados con OR en un solo title_filter
    # Así usamos 1 sola petición a la API en vez de 7
    terminos_busqueda = [
        "pentester",
        "red team",
        "blue team",
        "hacking ético",
        "ciberseguridad",
        "cybersecurity",
        "penetration tester",
    ]
    title_filter = " OR ".join(terminos_busqueda)

    print(f"🔍 Búsqueda LinkedIn (todos los términos en 1 llamada): {title_filter}")

    conn = http.client.HTTPSConnection("linkedin-job-search-api.p.rapidapi.com")

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "linkedin-job-search-api.p.rapidapi.com",
        "Content-Type": "application/json"
    }

    # Codificamos los parámetros para la URL
    title_encoded = urllib.parse.quote(title_filter)
    location_encoded = urllib.parse.quote("Spain")
    endpoint = f"/active-jb-24h?offset=0&title_filter={title_encoded}&location_filter={location_encoded}&description_type=text"

    try:
        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        raw_data = res.read()

        if res.status == 200:
            data = json.loads(raw_data.decode("utf-8"))

            # La API puede devolver una lista directa o un objeto con clave
            jobs = data if isinstance(data, list) else data.get("data", data.get("results", []))

            print(f"📦 LinkedIn: {len(jobs)} ofertas encontradas.")

            for j in jobs:
                job_id = j.get("id", "")
                # Ubicación: usamos locations_derived si existe, sino addressLocality
                ubicacion = ""
                locations_derived = j.get("locations_derived", [])
                if locations_derived:
                    ubicacion = ", ".join(locations_derived)
                elif j.get("locations_raw"):
                    for loc in j.get("locations_raw", []):
                        addr = loc.get("address", {})
                        ubicacion = addr.get("addressLocality", addr.get("addressCountry", ""))

                ofertas_totales.append({
                    "id": str(job_id) if job_id else "",
                    "titulo": j.get("title", ""),
                    "empresa": j.get("organization", "Empresa oculta"),
                    "ubicacion": ubicacion,
                    "descripcion": j.get("description_text", ""),
                    "enlace": j.get("url", ""),
                    "plataforma": "LinkedIn",
                    "es_remoto": j.get("remote_derived", False)
                })
        else:
            print(f"❌ Error API LinkedIn: {res.status} - {raw_data.decode('utf-8')}")
    except Exception as e:
        print(f"❌ Error en petición LinkedIn: {e}")
    finally:
        conn.close()

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
    import requests  # Solo se usa aquí para enviar a Telegram

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
            import time
            try:
                error_data = r.json()
                retry_after = error_data.get("parameters", {}).get("retry_after", 30)
            except:
                retry_after = 30
            print(f"⚠️ Rate Limit de Telegram. Esperando {retry_after} segundos...")
            time.sleep(retry_after)
            r = requests.post(url, json=payload) # Reintento
            
        if r.status_code != 200:
            print(f"❌ Error Telegram ({r.status_code}): {r.text}")
            return False
            
        return True
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")
        return False


# --- EJECUCIÓN ---
if __name__ == "__main__":
    ofertas_crudas = buscar_trabajos()
    filtradas = filtrar_ofertas(ofertas_crudas)

    print(f"🎯 Total tras filtros: {len(filtradas)}")

    nuevas = 0
    duplicadas = 0
    sin_id = 0

    for job in filtradas:
        job_id = job["id"]
        if job_id and not trabajo_ya_existe(job_id):
            exito = enviar_oferta_telegram(job)
            if exito:
                guardar_trabajo(job_id, job)
                print(f"📩 Enviada: {job['titulo']} en {job['empresa']}")
                nuevas += 1
            else:
                print(f"⚠️ Fallo al enviar a Telegram, no se guardó en BD: {job['titulo']}")
        elif job_id:
            print(f"⏭️ Ya existe en BD: {job['titulo']} en {job['empresa']}")
            duplicadas += 1
        else:
            print(f"⚠️ Oferta sin ID, omitida: {job['titulo']}")
            sin_id += 1

    print(f"\n📊 Resumen: {nuevas} nuevas enviadas | {duplicadas} ya en BD | {sin_id} sin ID")
