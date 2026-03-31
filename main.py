import os
import requests
import json

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_trabajos_ciberseguridad():
    print("Iniciando búsqueda en Google Jobs vía SerpApi...")
    
    # Parámetros exactos para la API
    params = {
        "engine": "google_jobs",
        # Agrupamos la experiencia y luego todas tus palabras clave de ciberseguridad
        "q": "(junior OR jr) (pentester OR \"red team\" OR \"blue team\" OR hacking OR ciberseguridad OR cybersecurity OR cibersecurity OR penetration)",
        "location": "Madrid, Spain",
        "hl": "es",
        "gl": "es",
        "chips": "date_posted:today", # Solo ofertas de hoy
        "api_key": SERPAPI_KEY
    }

    url = "https://serpapi.com/search.json"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Comprueba que no haya errores de conexión
        datos = response.json()
        
        # Extraemos la lista de trabajos (si no hay, devuelve una lista vacía)
        ofertas = datos.get("jobs_results", [])
        print(f"Se encontraron {len(ofertas)} ofertas en bruto. Aplicando filtros...")
        
        return ofertas

    except Exception as e:
        print(f"Error al conectar con la API: {e}")
        return []

def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    # Listas de palabras clave para el filtrado estricto
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    keywords_junior = ["junior", "jr", "trainee", "prácticas", "practicas", "entry level", "sin experiencia"]
    
    for oferta in ofertas:
        # Extraemos en minúsculas para facilitar la búsqueda
        titulo_lower = oferta.get('title', '').lower()
        descripcion = oferta.get('description', '').lower()
        ubicacion = oferta.get('location', '').lower()
        empresa = oferta.get('company_name', 'Empresa oculta')
        
        # 1. FILTRO ESTRICTO JUNIOR: Tiene que estar en el título o en la descripción
        es_junior = any(kw in titulo_lower or kw in descripcion for kw in keywords_junior)
        
        # 2. FILTRO FLEXIBILIDAD: Remoto o Híbrido
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        # 3. FILTRO UBICACIÓN: Madrid
        es_madrid = "madrid" in ubicacion or "madrid" in descripcion
        
        if es_junior and es_flexible and es_madrid:
            # --- ARREGLO DE LA URL ---
            enlace = "Enlace no disponible"
            apply_options = oferta.get("apply_options", [])
            
            # Buscamos los enlaces directos de aplicación (LinkedIn, web de empresa, etc.)
            if apply_options and len(apply_options) > 0:
                enlace = apply_options[0].get("link", "Enlace no disponible")
            else:
                # Como plan B, usamos el related_link o share_link
                enlace = oferta.get("share_link", "Enlace no disponible")
                
            ofertas_validas.append({
                "titulo": oferta.get('title', 'Sin título'), # Guardamos el título original con mayúsculas
                "empresa": empresa,
                "ubicacion": oferta.get('location', 'Madrid'),
                "enlace": enlace
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
    todas_las_ofertas = buscar_trabajos_ciberseguridad()
    ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
    
    print(f"Enviando {len(ofertas_filtradas)} ofertas válidas a Telegram...")
    
    for trabajo in ofertas_filtradas:
        enviar_oferta_telegram(trabajo)
