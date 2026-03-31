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
        # Usamos operadores booleanos en la búsqueda
        "q": "junior (pentester OR \"red team\" OR \"blue team\")",
        "location": "Madrid, Spain",
        "hl": "es", # Idioma español
        "gl": "es", # Región España
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
    
    # Palabras clave que queremos encontrar
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    
    for oferta in ofertas:
        titulo = oferta.get('title', 'Sin título')
        empresa = oferta.get('company_name', 'Empresa oculta')
        # Google Jobs a veces da la descripción o fragmentos (snippets)
        descripcion = oferta.get('description', '').lower()
        ubicacion = oferta.get('location', '').lower()
        
        # 1. Comprobamos flexibilidad (Remoto o Híbrido)
        # Buscamos si alguna de nuestras palabras clave está en la descripción o en la ubicación
        es_flexible = any(keyword in descripcion for keyword in keywords_flexibilidad) or \
                      any(keyword in ubicacion for keyword in keywords_flexibilidad)
        
        # 2. Comprobamos que sea Madrid (aunque la API ya filtra, nos aseguramos)
        es_madrid = "madrid" in ubicacion or "madrid" in descripcion
        
        if es_flexible and es_madrid:
            ofertas_validas.append({
                "titulo": titulo,
                "empresa": empresa,
                "ubicacion": oferta.get('location', 'Madrid'),
                # Link directo para aplicar
                "enlace": oferta.get('share_link', 'Enlace no disponible') 
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
