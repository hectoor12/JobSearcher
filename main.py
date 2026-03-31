import os
import requests
import json
import html

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_trabajos():
    print("Iniciando búsqueda amplia en Google Jobs (Última semana)...")
    
    params = {
        "engine": "google_jobs",
        "q": "pentester OR \"red team\" OR \"blue team\" OR hacking OR ciberseguridad OR cybersecurity OR penetration",
        "location": "Madrid, Spain",
        "hl": "es",
        "gl": "es",
        "chips": "date_posted:week",
        "api_key": SERPAPI_KEY
    }

    url = "https://serpapi.com/search.json"
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get("jobs_results", [])
    except Exception as e:
        print(f"Error al buscar en la API: {e}")
        return []

def obtener_enlace_directo(job_id):
    """Hace una segunda llamada a SerpAPI con el job_id para obtener el enlace directo."""
    params = {
        "engine": "google_jobs_listing",
        "q": job_id,
        "api_key": SERPAPI_KEY
    }
    try:
        response = requests.get("https://serpapi.com/search.json", params=params)
        response.raise_for_status()
        data = response.json()
        # El enlace directo viene en apply_options de este endpoint
        for opcion in data.get("apply_options", []):
            link = opcion.get("link", "")
            if link and "google.com" not in link:
                return link
    except Exception as e:
        print(f"Error obteniendo enlace directo para job_id {job_id}: {e}")
    return None

def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect", "arquitecto", "expert"]
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    ciudades_permitidas = ["madrid", "alcobendas", "pozuelo", "las rozas", "getafe", "leganés"]

    for oferta in ofertas:
        titulo = oferta.get('title', '').lower()
        descripcion = oferta.get('description', '').lower()
        ubicacion = oferta.get('location', '').lower()
        
        es_senior = any(word in titulo for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona and es_flexible:

            enlace_final = None

            # 1. Intentamos sacar enlace directo de apply_options (sin pasar por Google)
            for opcion in oferta.get("apply_options", []):
                link = opcion.get("link", "")
                if link and "google.com" not in link:
                    enlace_final = link
                    break

            # 2. Si no hay enlace directo, hacemos segunda llamada con el job_id
            if not enlace_final:
                job_id = oferta.get("job_id") or oferta.get("id")
                if job_id:
                    print(f"  → Buscando enlace directo para: {oferta.get('title', '')}")
                    enlace_final = obtener_enlace_directo(job_id)

            # 3. Último recurso: share_link solo si no es una búsqueda de Google
            if not enlace_final:
                share = oferta.get("share_link", "")
                if share and "google.com/search" not in share:
                    enlace_final = share

            plataforma_limpia = oferta.get('via', 'Desconocida').replace("via ", "").replace("vía ", "")

            ofertas_validas.append({
                "titulo": oferta.get('title', 'Sin título'),
                "empresa": oferta.get('company_name', 'Empresa oculta'),
                "ubicacion": oferta.get('location', 'Ubicación no especificada'),
                "plataforma": plataforma_limpia,
                "enlace": enlace_final
            })
            
    return ofertas_validas

def enviar_oferta_telegram(oferta):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    texto = f"🚨 <b>Nueva Oferta:</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    
    if oferta.get('enlace'):
        texto += f"🔗 <a href='{html.escape(oferta['enlace'])}'>Haz clic aquí para aplicar</a>"
    else:
        texto += f"🔗 Busca la oferta en <b>{html.escape(oferta['plataforma'])}</b>"
    
    teclado = {
        "inline_keyboard": [
            [
                {"text": "✅ Aplicar", "callback_data": "accion_aplicar"},
                {"text": "❌ Descartar", "callback_data": "accion_descartar"}
            ]
        ]
    }
    
    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(teclado)
    }
    
    try:
        respuesta = requests.post(url, data=payload)
        respuesta.raise_for_status()
        print(f"Mensaje enviado con éxito: {oferta['titulo']}")
    except Exception as e:
        print(f"Error al enviar a Telegram ({oferta['titulo']}): {e}")

# --- EJECUCIÓN DEL SCRIPT ---
if __name__ == "__main__":
    if not SERPAPI_KEY or not TELEGRAM_TOKEN or not CHAT_ID:
        print("¡ERROR! Faltan variables de entorno. Revisa tus Secrets en GitHub.")
    else:
        todas_las_ofertas = buscar_trabajos()
        ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
        
        print(f"Enviando {len(ofertas_filtradas)} ofertas válidas a Telegram...")
        
        for trabajo in ofertas_filtradas:
            enviar_oferta_telegram(trabajo)
