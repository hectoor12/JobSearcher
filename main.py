import os
import requests
import json
import html
from urllib.parse import quote_plus

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
        for opcion in data.get("apply_options", []):
            link = opcion.get("link", "")
            if link and "google.com" not in link:
                return link
    except Exception as e:
        print(f"Error obteniendo enlace directo para job_id {job_id}: {e}")
    return None

def construir_enlace_fallback(titulo, empresa, plataforma):
    """Si no hay enlace directo, construye una búsqueda en la plataforma correspondiente."""
    query = quote_plus(f"{titulo} {empresa}")
    plataforma_lower = plataforma.lower()

    if "linkedin" in plataforma_lower:
        return f"https://www.linkedin.com/jobs/search/?keywords={query}&location=Madrid"
    elif "infojobs" in plataforma_lower:
        return f"https://www.infojobs.net/jobsearch/search-results/list.xhtml?keyword={query}"
    elif "indeed" in plataforma_lower:
        return f"https://es.indeed.com/jobs?q={query}&l=Madrid"
    elif "glassdoor" in plataforma_lower:
        return f"https://www.glassdoor.es/Empleo/madrid-{quote_plus(titulo.lower())}-empleos-SRCH_IL.0,6_IC3162622.htm"
    elif "tecnoempleo" in plataforma_lower:
        return f"https://www.tecnoempleo.com/busqueda-empleo.php?te={query}&pr=Madrid"
    else:
        # Búsqueda genérica en Google directamente a la oferta
        return f"https://www.google.com/search?q={quote_plus(titulo + ' ' + empresa + ' trabajo Madrid')}"

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
            titulo_real = oferta.get('title', 'Sin título')
            empresa_real = oferta.get('company_name', '')
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
                    print(f"  → Buscando enlace directo para: {titulo_real}")
                    enlace_final = obtener_enlace_directo(job_id)

            # 3. share_link si no es búsqueda de Google
            if not enlace_final:
                share = oferta.get("share_link", "")
                if share and "google.com/search" not in share:
                    enlace_final = share

            # 4. Fallback: enlace de búsqueda en la plataforma correspondiente
            if not enlace_final or "google.com/search" in enlace_final:
                print(f"  → Construyendo enlace fallback para: {titulo_real}")
                enlace_final = construir_enlace_fallback(titulo_real, empresa_real, plataforma_limpia)

            ofertas_validas.append({
                "titulo": titulo_real,
                "empresa": empresa_real or "Empresa oculta",
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
```

Ahora el flujo es: enlace directo → segunda llamada SerpAPI → share_link → **búsqueda en la plataforma correcta**. Para el caso que pusiste (`Ingeniero/a CyberArk` en LinkedIn), generaría este enlace:
```
https://www.linkedin.com/jobs/search/?keywords=Ingeniero%2Fa+CyberArk+IOON&location=Madrid
