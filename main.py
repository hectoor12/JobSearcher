import os
import requests
import json

# Cargamos las variables de entorno (solo una vez)
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
        
        # 1. Filtro de Nivel (No Senior)
        es_senior = any(word in titulo for word in palabras_prohibidas)
        
        # 2. Filtro de Ubicación
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        
        # 3. Filtro de Flexibilidad
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona and es_flexible:
            
            # --- CORRECCIÓN DEFINITIVA DEL ENLACE (Limpia y sin errores) ---
            enlace_final = None
            opciones_aplicar = oferta.get("apply_options", [])
            links_relacionados = oferta.get("related_links", [])
            
            # Prioridad 1: Botón directo de aplicar
            if opciones_aplicar:
                enlace_final = opciones_aplicar[0].get("link")
            # Prioridad 2: Enlaces relacionados
            elif links_relacionados:
                enlace_final = links_relacionados[0].get("link")
            # Prioridad 3: El enlace por defecto de compartir
            else:
                enlace_final = oferta.get("share_link")

            # Solo añadimos si hemos conseguido un enlace
            if enlace_final:
                ofertas_validas.append({
                    "titulo": oferta.get('title', 'Sin título'),
                    "empresa": oferta.get('company_name', 'Empresa oculta'),
                    "ubicacion": oferta.get('location', 'Ubicación no especificada'),
                    "enlace": enlace_final
                })
            
    return ofertas_validas

def enviar_oferta_telegram(oferta):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Formateamos el mensaje
    texto = f"🚨 *Nueva Oferta: {oferta['titulo']}*\n"
    texto += f"🏢 *Empresa:* {oferta['empresa']}\n"
    texto += f"📍 *Ubicación:* {oferta['ubicacion']}\n"
    texto += f"🔗 [Haz clic aquí para aplicar]({oferta['enlace']})"
    
    # Teclado en línea
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
        "parse_mode": "Markdown",
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
