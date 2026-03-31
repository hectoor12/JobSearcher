import os
import requests
import serpapi
import html

# --- CREDENCIALES ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- 1. BÚSQUEDA (Solo Google Jobs) ---
def buscar_trabajos():
    client = serpapi.Client(api_key=SERPAPI_KEY)
    try:
        results = client.search({
            "engine": "google_jobs",
            "q": 'pentester OR "red team" OR "blue team" OR hacking OR ciberseguridad OR cybersecurity OR penetration',
            "location": "Madrid, Spain",
            "gl": "es",
            "hl": "es",
            "chips": "date_posted:day"
        })
        
        ofertas = []
        for j in results.get("jobs_results", []):
            # Priorizamos el source_link, si no existe buscamos en apply_options
            link = j.get("source_link")
            if not link and j.get("apply_options"):
                link = j.get("apply_options")[0].get("link")
            
            ofertas.append({
                "titulo": j.get("title", ""),
                "empresa": j.get("company_name", "Empresa oculta"),
                "ubicacion": j.get("location", ""),
                "descripcion": j.get("description", ""),
                "enlace": link,
                "plataforma": j.get("via", "Google Jobs").replace("via ", "").replace("vía ", "")
            })
        return ofertas
    except Exception:
        return []

# --- 2. FILTRADO ---
def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect", "arquitecto", "expert"]
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    ciudades_permitidas = ["madrid", "comunidad de madrid", "españa", "spain", "alcobendas", "pozuelo", "las rozas", "getafe", "leganés", "móstoles"]

    for oferta in ofertas:
        titulo = oferta["titulo"].lower()
        descripcion = oferta["descripcion"].lower()
        ubicacion = oferta["ubicacion"].lower()
        
        es_senior = any(word in titulo.split() for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona:
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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    if SERPAPI_KEY and TELEGRAM_TOKEN and CHAT_ID:
        todas = buscar_trabajos()
        
        if todas:
            filtradas = filtrar_ofertas(todas)
            
            vistas = set()
            for trabajo in filtradas:
                id_unico = f"{trabajo['titulo']}{trabajo['empresa']}".lower()
                if id_unico not in vistas:
                    enviar_oferta_telegram(trabajo)
                    vistas.add(id_unico)
    else:
        print("Error: Faltan variables de entorno (API Keys o Chat ID)")
