import os
import requests
import json
import html # Añadimos esta librería nativa para evitar errores con caracteres especiales en Telegram

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
            
            # --- EXTRACCIÓN DEL ENLACE ---
            enlace_final = None
            opciones_aplicar = oferta.get("apply_options", [])
            links_relacionados = oferta.get("related_links", [])
            
            if opciones_aplicar:
                enlace_final = opciones_aplicar[0].get("link")
            elif links_relacionados:
                enlace_final = links_relacionados[0].get("link")
            else:
                enlace_final = oferta.get("share_link")

            # --- EXTRACCIÓN DE LA PLATAFORMA ---
            # Google devuelve algo como "via LinkedIn". Lo limpiamos para que quede solo "LinkedIn"
            plataforma_bruta = oferta.get('via', 'Plataforma desconocida')
            plataforma_limpia = plataforma_bruta.replace("via ", "").replace("vía ", "")

            if enlace_final:
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
    
    # Formateamos el mensaje en HTML para que no se rompan los enlaces largos de LinkedIn/InfoJobs
    # html.escape() protege caracteres como "<" o ">" si vienen en el título del trabajo
    texto = f"🚨 <b>Nueva Oferta: {html.escape(oferta['titulo'])}</b>\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{oferta['enlace']}'>Haz clic aquí para aplicar</a>"
    
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
        "parse_mode": "HTML", # Cambiado de Markdown a HTML (A prueba de balas)
        "reply_markup": json.dumps(teclado)
    }
    
    try:
        respuesta = requests.post(url, data=payload)
        respuesta.raise_for_status()
        print(f"Mensaje enviado con éxito: {oferta['titulo']}")
    except Exception as e:
        print(f"Error al enviar a Telegram ({oferta['titulo']}): {e}")

if __name__ == "__main__":
    if not SERPAPI_KEY or not TELEGRAM_TOKEN or not CHAT_ID:
        print("¡ERROR! Faltan variables de entorno. Revisa tus Secrets en GitHub.")
    else:
        todas_las_ofertas = buscar_trabajos()
        ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
        
        print(f"Enviando {len(ofertas_filtradas)} ofertas válidas a Telegram...")
        
        for trabajo in ofertas_filtradas:
            enviar_oferta_telegram(trabajo)
