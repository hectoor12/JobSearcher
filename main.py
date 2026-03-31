import os
import requests
import json

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

import os
import requests
import json

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

def buscar_trabajos():
    print("Iniciando búsqueda amplia en Google Jobs (Última semana)...")
    
    params = {
        "engine": "google_jobs",
        # Quitamos 'junior' de la búsqueda principal para que Google nos dé TODO
        "q": "pentester OR \"red team\" OR \"blue team\" OR hacking OR ciberseguridad OR cybersecurity OR penetration",
        "location": "Madrid, Spain",
        "hl": "es",
        "gl": "es",
        "chips": "date_posted:week", # Ampliamos a la semana para no perder nada
        "api_key": SERPAPI_KEY
    }

    url = "https://serpapi.com/search.json"
    response = requests.get(url, params=params)
    return response.json().get("jobs_results", [])

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
            
            # --- CORRECCIÓN DEFINITIVA DEL ENLACE ---
            # Google Jobs guarda los enlaces reales en 'apply_options'
            opciones_aplicar = oferta.get("apply_options", [])
            enlace_final = None

            if opciones_aplicar:
                # Intentamos coger el primer enlace de la lista (suele ser el más directo)
                enlace_final = opciones_aplicar[0].get("link")
            
            # Si por lo que sea no hay apply_options, buscamos en related_links
            if not enlace_final:
                links_relacionados = oferta.get("related_links", [])
                if links_relacionados:
                    enlace_final = links_relacionados[0].get("link")

            # Si sigue sin haber nada (raro), usamos el share_link como último recurso
            if not enlace_final:
                enlace_final = oferta.get("share_link")

            # Solo añadimos si hemos conseguido un enlace que no sea None
            if enlace_final:
                ofertas_validas.append({
                    "titulo": oferta.get('title'),
                    "empresa": oferta.get('company_name'),
                    "ubicacion": oferta.get('location'),
                    "enlace": enlace_final
                })
            
    return ofertas_validas

def enviar_oferta_telegram(oferta):
    # Endpoint oficial de la API de Telegram para enviar mensajes
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Formateamos el mensaje con Markdown para que se vea bonito
    texto = f"🚨 *Nueva Oferta: {oferta['titulo']}*\n"
    texto += f"🏢 *Empresa:* {oferta['empresa']}\n"
    texto += f"📍 *Ubicación:* {oferta['ubicacion']}\n"
    texto += f"🔗 [Enlace a la oferta]({oferta['enlace']})"
    
    # Creamos el teclado en línea (Inline Keyboard)
    teclado = {
        "inline_keyboard": [
            [
                # callback_data es lo que leerá PythonAnywhere cuando pulses el botón
                {"text": "✅ Aplicar", "callback_data": "accion_aplicar"},
                {"text": "❌ Descartar", "callback_data": "accion_descartar"}
            ]
        ]
    }
    
    # Preparamos el paquete de datos
    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(teclado)
    }
    
    # Disparamos el mensaje hacia Telegram
    try:
        respuesta = requests.post(url, data=payload)
        respuesta.raise_for_status()
        print(f"Mensaje enviado con éxito: {oferta['titulo']}")
    except Exception as e:
        print(f"Error al enviar a Telegram: {e}")

# --- EJECUCIÓN DEL SCRIPT ---
# --- EJECUCIÓN DEL SCRIPT ---
if __name__ == "__main__":
    todas_las_ofertas = buscar_trabajos()
    ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
    
    print(f"Enviando {len(ofertas_filtradas)} ofertas válidas a Telegram...")
    
    for trabajo in ofertas_filtradas:
        enviar_oferta_telegram(trabajo)
