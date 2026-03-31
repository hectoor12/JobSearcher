import os
import requests
import json
import html

# Cargamos las variables de entorno
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

def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    # Listas de control
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect", "arquitecto", "expert"]
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    ciudades_permitidas = ["madrid", "alcobendas", "pozuelo", "las rozas", "getafe", "leganés"]

    for oferta in ofertas:
        titulo = oferta.get('title', '').lower()
        descripcion = oferta.get('description', '').lower()
        ubicacion = oferta.get('location', '').lower()
        
        # 1. Filtros
        es_senior = any(word in titulo for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona and es_flexible:
            
            # --- EXTRACCIÓN Y LIMPIEZA DEL ENLACE ---
            enlace_final = None
            
            # Prioridad 1: Enlace directo a la plataforma (LinkedIn, InfoJobs, etc.)
            opciones_aplicar = oferta.get("apply_options", [])
            for opcion in opciones_aplicar:
                link = opcion.get("link", "")
                if link and "google.com/search" not in link:
                    enlace_final = link
                    break
                    
            # Prioridad 2: Enlaces relacionados sin basura de Google
            if not enlace_final:
                links_relacionados = oferta.get("related_links", [])
                for rel in links_relacionados:
                    link = rel.get("link", "")
                    if link and "google.com/search" not in link:
                        enlace_final = link
                        break

            # Prioridad 3: Fabricamos enlace corto y limpio de Google Jobs con el ID
            if not enlace_final:
                job_id = oferta.get("job_id")
                if job_id:
                    enlace_final = f"https://www.google.com/search?htivrt=jobs&htidocid={job_id}"
                else:
                    enlace_final = oferta.get("share_link", "Enlace no disponible")

            # --- EXTRACCIÓN DE LA PLATAFORMA ---
            plataforma_bruta = oferta.get('via', 'Plataforma desconocida')
            plataforma_limpia = plataforma_bruta.replace("via ", "").replace("vía ", "")

            # Guardamos la oferta solo si logramos rescatar un enlace válido
            if enlace_final and enlace_final != "Enlace no disponible":
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
    
    # Construimos el mensaje en HTML puro asegurando que los caracteres raros no rompan la estructura
    texto = f"🚨 <b>Nueva Oferta:</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{oferta['enlace']}'>Haz clic aquí para aplicar</a>"
    
    # Teclado con botones
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
