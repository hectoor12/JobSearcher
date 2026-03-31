import os
import requests
import serpapi
import html

# --- CREDENCIALES ---
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- 1. BÚSQUEDA ---
def buscar_trabajos():
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
    except Exception:
        return []

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
        
        es_senior = any(word in titulo.split() for word in palabras_prohibidas)
        en_zona = any(ciudad in ubicacion or ciudad in descripcion for ciudad in ciudades_permitidas)
        es_flexible = any(kw in descripcion or kw in ubicacion for kw in keywords_flexibilidad)
        
        if not es_senior and en_zona and es_flexible:
            titulo_real = oferta.get('title', 'Sin título')
            empresa_real = oferta.get('company_name', 'Empresa oculta')
            plataforma_limpia = oferta.get('via', 'Desconocida').replace("via ", "").replace("vía ", "").replace("a través de ", "")

            # Extraemos directamente el source_link (o buscamos en apply_options por si acaso alguna oferta no lo trae)
            enlace_final = oferta.get("source_link")
            if not enlace_final and oferta.get("apply_options"):
                enlace_final = oferta.get("apply_options")[0].get("link", "Sin enlace")

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
        requests.post(url, json=payload)
    except Exception:
        pass  # Falla silenciosamente sin romper el script

# --- EJECUCIÓN DEL SCRIPT ---
if __name__ == "__main__":
    if SERPAPI_KEY and TELEGRAM_TOKEN and CHAT_ID:
        todas_las_ofertas = buscar_trabajos()
        if todas_las_ofertas:
            ofertas_filtradas = filtrar_ofertas(todas_las_ofertas)
            for trabajo in ofertas_filtradas:
                enviar_oferta_telegram(trabajo)
