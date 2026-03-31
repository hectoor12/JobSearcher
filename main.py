import os
import requests
import serpapi
import html
import json
import urllib.parse

# --- CREDENCIALES ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- 1. BÚSQUEDA ---
def buscar_trabajos():
    print("Iniciando búsqueda amplia en Google Jobs (Última semana)...")
    
    client = serpapi.Client(api_key=SERPAPI_KEY)
    
    try:
        results = client.search({
            "engine": "google_jobs",
            "q": 'pentester OR "red team" OR "blue team" OR hacking OR ciberseguridad OR cybersecurity OR penetration',
            "location": "Madrid, Spain",
            "google_domain": "google.es",
            "hl": "es",
            "gl": "es",
            "chips": "date_posted:week"
        })
        
        return results.get("jobs_results", [])
        
    except Exception as e:
        print(f"Error al buscar en la API: {e}")
        return []

# --- FUNCIONES AUXILIARES PARA ENLACES ---
def obtener_enlace_directo(job_id):
    # Función de apoyo si se quiere hacer una segunda llamada a la API por job_id
    return None

def construir_enlace_fallback(titulo, empresa, plataforma):
    # Crea una búsqueda en Google normal si no hay enlace directo
    query = f"{titulo} {empresa} {plataforma}"
    return f"https://www.google.com/search?q={urllib.parse.quote(query)}"

# --- 2. FILTRADO ---
def filtrar_ofertas(ofertas):
    ofertas_validas = []
    
    palabras_prohibidas = ["senior", "sr", "lead", "principal", "manager", "director", "architect", "arquitecto", "expert"]
    keywords_flexibilidad = ["remoto", "remote", "híbrido", "hibrido", "hybrid", "teletrabajo"]
    ciudades_permitidas = ["madrid", "alcobendas", "pozuelo", "las rozas", "getafe", "leganés"]

    for oferta in ofertas:
        titulo = oferta.get('title', '').lower()
        descripcion = oferta.get('description', '').lower()
        ubicacion = oferta.get('location', '').lower()
        
        # Filtros
        es_senior = any(word in titulo.split() for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona and es_flexible:
            enlace_final = None
            titulo_real = oferta.get('title', 'Sin título')
            empresa_real = oferta.get('company_name', 'Empresa oculta')
            plataforma_limpia = oferta.get('via', 'Desconocida').replace("via ", "").replace("vía ", "").replace("a través de ", "")

            # 1. Enlace directo desde apply_options
            for opcion in oferta.get("apply_options", []):
                link = opcion.get("link", "")
                if link and "google.com" not in link:
                    enlace_final = link
                    break

            # 2. Segunda llamada con job_id
            if not enlace_final:
                job_id = oferta.get("job_id") or oferta.get("id")
                if job_id:
                    enlace_final = obtener_enlace_directo(job_id)

            # 3. share_link si no es búsqueda de Google
            if not enlace_final:
                share = oferta.get("share_link", "")
                if share and "google.com/search" not in share:
                    enlace_final = share

            # 4. Fallback: enlace de búsqueda
            if not enlace_final or "google.com/search" in enlace_final:
                enlace_final = construir_enlace_fallback(titulo_real, empresa_real, plataforma_limpia)

            ofertas_validas.append({
                "titulo": titulo_real,
                "empresa": empresa_real,
                "ubicacion": oferta.get('location', 'Ubicación no especificada'),
                "plataforma": plataforma_limpia,
                "enlace": enlace_final
            })
            
    return ofertas_validas

# --- 3. ENVÍO A TELEGRAM ---
def enviar_oferta_telegram(oferta):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    texto = f"🚨 <b>Nueva Oferta:</b> {html.escape(oferta['titulo'])}\n"
    texto += f"🏢 <b>Empresa:</b> {html.escape(oferta['empresa'])}\n"
    texto += f"📍 <b>Ubicación:</b> {html.escape(oferta['ubicacion'])}\n"
    texto += f"🌐 <b>Plataforma:</b> {html.escape(oferta['plataforma'])}\n\n"
    texto += f"🔗 <a href='{html.escape(oferta['enlace'])}'>Haz clic aquí para aplicar</a>"
    
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
        "reply_markup": teclado
    }
    
    try:
        respuesta = requests.post(url, json=payload)
        respuesta.raise_for_status()
        print(f"Mensaje enviado con éxito: {oferta['titulo']}")
    except Exception as e:
        print(f"Error al enviar a Telegram ({oferta['titulo']}): {e}")

# --- EJECUCIÓN DEL SCRIPT ---
if __name__ == "__main__":
    if not SERPAPI_KEY or not TELEGRAM_TOKEN or not CHAT_ID:
        print("¡ERROR! Faltan variables de entorno.")
        print("Asegúrate de haber configurado SERPAPI_KEY, TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.")
    else:
        todas_las_ofertas = buscar_trabajos()
        
        # Imprime toda la salida cruda de la API para que puedas revisarla
        print("\n--- SALIDA CRUDA DE JOBS_RESULTS ---")
        print(json.dumps(todas_las_ofertas, indent=4, ensure_ascii=False))
        print("--------------------------------------\n")
        
        if todas_las_ofertas:
            ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
            print(f"Enviando {len(ofertas_filtradas)} ofertas válidas a Telegram...")
            
            for trabajo in ofertas_filtradas:
                enviar_oferta_telegram(trabajo)
        else:
            print("No se encontraron ofertas en esta búsqueda.")
