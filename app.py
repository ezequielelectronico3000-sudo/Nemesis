import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify 
from urllib.parse import urljoin, urlparse
from collections import Counter 
import re 
import os 
import json 
from dotenv import load_dotenv

# --- CARGA LA CLAVE API DESDE EL ARCHIVO .ENV ---
load_dotenv() 
# ------------------------------------------------

app = Flask(__name__)

# Lista básica de "stopwords" en español
STOPWORDS_ES = set([
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'pero', 
    'si', 'de', 'del', 'al', 'en', 'es', 'son', 'por', 'para', 'con', 'a', 
    'su', 'sus', 'lo', 'le', 'les', 'me', 'se', 'mi', 'mis', 'tu', 'tus', 
    'nos', 'os', 'no', 'que', 'como', 'más', 'esos', 'esas', 'este', 'esta',
    'estos', 'estas', 'ser', 'ha', 'han', 'haber', 'hacer', 'tener', 'poder',
    'todo', 'todos', 'toda', 'todas', 'donde', 'cuando', 'quien', 'cual',
    'sin', 'sobre', 'bajo', 'entre', 'hasta', 'desde', 'muy', 'tal', 'vez',
    'solo', 'sólo'
])

# ----------------------------------------------------------------------
# FUNCIONES AUXILIARES (DE ANÁLISIS)
# ----------------------------------------------------------------------
def extraer_encabezados(soup):
    """Extrae el texto de todas las etiquetas H1 a H6 y las cuenta."""
    encabezados = {}
    tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    for tag in tags:
        found_tags = soup.find_all(tag)
        if found_tags:
            encabezados[tag] = {
                'conteo': len(found_tags),
                'textos': [h.get_text(strip=True) for h in found_tags]
            }
        else:
            encabezados[tag] = {'conteo': 0, 'textos': []}
    return encabezados

def extract_filename_from_url(url):
    """Extrae el nombre base del archivo de una URL."""
    url = url.split('?')[0]
    filename = os.path.basename(url)
    if not filename or '.' not in filename:
        if '.css' in url.lower(): return "archivo_descargado.css"
        elif '.js' in url.lower(): return "archivo_descargado.js"
        return "archivo_descargado.txt"
    return filename

def generate_short_name(full_name):
    """Genera un nombre corto y legible para mostrar en el botón."""
    name_parts = full_name.split('.')
    extension = name_parts[-1].lower() if len(name_parts) > 1 else 'txt'
    file_type = {'css': 'Estilo', 'js': 'Script'}.get(extension, 'Archivo')
    base_name = name_parts[0]
    short_name = base_name[:10] + '...' if len(base_name) > 10 else base_name
    return f"{file_type}: {short_name}.{extension}"

def obtener_contenido_recurso(url_base, path):
    """Descarga el contenido de un recurso externo (CSS/JS)."""
    full_url = urljoin(url_base, path)
    try:
        response = requests.get(full_url, timeout=5)
        response.raise_for_status() 
        nombre_descarga = extract_filename_from_url(full_url)
        nombre_corto = generate_short_name(nombre_descarga) 
        return response.text, full_url, nombre_descarga, nombre_corto
    except requests.exceptions.RequestException:
        return None, full_url, None, None

def contar_palabras_clave(soup):
    """Extrae, limpia y cuenta las 10 palabras más frecuentes en el contenido visible."""
    texts = soup.find_all(text=True) 
    def visible(element):
        if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']: return False
        if isinstance(element, type(soup.comment)): return False
        return True
    visible_texts = filter(visible, texts)
    full_text = " ".join(t.strip() for t in visible_texts if t.strip())
    cleaned_text = re.sub(r'[^a-záéíóúüñ\s]', '', full_text.lower())
    words = cleaned_text.split()
    meaningful_words = [word for word in words if word not in STOPWORDS_ES and len(word) > 1]
    word_counts = Counter(meaningful_words)
    top_10 = word_counts.most_common(10)
    return [{'palabra': word, 'conteo': count} for word, count in top_10]

def extraer_metadatos(soup):
    """Extrae las principales etiquetas meta de la sección <head> para análisis SEO."""
    metadatos = {
        'description': 'No encontrado',
        'keywords': 'No encontradas',
        'author': 'No encontrado',
        'charset': soup.find('meta', charset=True).get('charset', 'No encontrado') if soup.find('meta', charset=True) else 'No encontrado',
        'og_image': None 
    }
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        content = meta.get('content', '')
        if name == 'description' and content: metadatos['description'] = content.strip()
        elif name == 'keywords' and content: metadatos['keywords'] = content.strip()
        elif name == 'author' and content: metadatos['author'] = content.strip()
            
    og_desc = soup.find('meta', property='og:description')
    if og_desc and og_desc.get('content') and metadatos['description'] == 'No encontrado':
        metadatos['description'] = f"OG Description: {og_desc.get('content').strip()}"
    og_image = soup.find('meta', property='og:image')
    if og_image and og_image.get('content'):
        metadatos['og_image'] = og_image.get('content')
    return metadatos

def analizar_imagenes(soup):
    """Cuenta el total de imágenes y aquellas que faltan el atributo 'alt'."""
    imagenes = soup.find_all('img')
    total_imagenes = len(imagenes)
    sin_alt = sum(1 for img in imagenes if not img.get('alt', '').strip())
    return {
        'total_imagenes': total_imagenes,
        'imagenes_sin_alt': sin_alt,
        'porcentaje_sin_alt': round((sin_alt / total_imagenes) * 100, 2) if total_imagenes > 0 else 0
    }

def detectar_contenido_inline(soup):
    """Detecta la presencia de bloques de CSS o JS directamente en la página."""
    style_blocks = soup.find_all('style')
    css_inline_count = len(style_blocks)
    script_blocks = [s for s in soup.find_all('script') if not s.get('src') and s.get_text(strip=True)]
    js_inline_count = len(script_blocks)
    return {
        'css_inline_blocks': css_inline_count,
        'js_inline_blocks': js_inline_count,
        'js_inline_texto_muestra': [s.get_text(strip=True)[:50] + '...' for s in script_blocks]
    }

def buscar_etiquetas_obsoletas(soup):
    """Busca etiquetas HTML obsoletas o desaconsejadas (mayormente estilísticas)."""
    obsoletas = ['font', 'center', 'strike', 'u', 'b', 'i'] 
    encontradas = {}
    for tag in obsoletas:
        conteo = len(soup.find_all(tag))
        if conteo > 0:
            encontradas[tag] = conteo
    return encontradas

def analizar_enlaces_tabnabbing(soup):
    """Detecta enlaces (<a>) con target="_blank" que carecen de rel="noopener noreferrer"."""
    enlaces_riesgo = []
    enlaces = soup.find_all('a', target='_blank')
    for link in enlaces:
        rel = link.get('rel', '')
        rel_str = ' '.join(rel) if isinstance(rel, list) else rel
        if 'noopener' not in rel_str.lower() or 'noreferrer' not in rel_str.lower():
            enlaces_riesgo.append({
                'texto': link.get_text(strip=True)[:50] + '...' if len(link.get_text(strip=True)) > 50 else link.get_text(strip=True),
                'href': link.get('href', 'URL no definida')
            })
    return enlaces_riesgo

def analizar_iframes(soup):
    """Detecta iframes y verifica dominios de alto riesgo o no seguros."""
    iframes = soup.find_all('iframe')
    analisis_iframes = {
        'total_iframes': len(iframes),
        'iframes_inseguros': [],
        'dominios_riesgo': []
    }
    dominios_de_riesgo = ['htmlpreview.github.io', 'docs.google.com/forms', 'embed.ly', 'codepen.io']
    for iframe in iframes:
        src = iframe.get('src', '').lower()
        if not src:
            analisis_iframes['iframes_inseguros'].append('iframe sin atributo src')
            continue
        if 'htmlpreview.github.io' in src:
            analisis_iframes['dominios_riesgo'].append(f"CRÍTICO: {src} (Usando htmlpreview.github.io para contenido)")
        for dominio in dominios_de_riesgo:
            if dominio in src and 'htmlpreview.github.io' not in src:
                analisis_iframes['dominios_riesgo'].append(f"ALERTA: {src} (Dominio de vista previa/embed)")
    return analisis_iframes

def analizar_seguridad_basica(css_archivos, js_archivos, recursos_fallidos):
    """Revisa los recursos externos y su contenido en busca de problemas básicos de seguridad."""
    inseguro_http = []
    riesgo_js = []
    for recurso_list in [css_archivos, js_archivos]:
        for recurso in recurso_list:
            if recurso['url'].startswith('http://'):
                inseguro_http.append(recurso['url'])
    for recurso in recursos_fallidos:
        if recurso['url'].startswith('http://'):
            if recurso['url'] not in inseguro_http:
                inseguro_http.append(recurso['url'])
    for js_file in js_archivos:
        contenido = js_file.get('contenido', '')
        nombre_corto = js_file['nombre_corto']
        if 'eval(' in contenido or 'document.write(' in contenido:
            riesgo_js.append(nombre_corto)
        if "document.execCommand('copy')" in contenido or "document.execCommand('cut')" in contenido:
            if nombre_corto not in riesgo_js: 
                riesgo_js.append(f"ALERTA OBSOLETA: {nombre_corto} (Usa execCommand)")
    return {
        'recursos_http_inseguros': inseguro_http,
        'riesgo_js_detectado': riesgo_js
    }

def analizar_cabeceras_seguridad(cabeceras):
    """
    Revisa las cabeceras de respuesta HTTP en busca de políticas de seguridad clave.
    """
    cabeceras_analisis = {}
    # Convertir las claves a mayúsculas para asegurar la búsqueda
    cabeceras_upper = {k.upper(): v for k, v in cabeceras.items()}
    
    cabeceras_analisis['CSP'] = cabeceras_upper.get('CONTENT-SECURITY-POLICY', 'AUSENTE: RIESGO ALTO').strip()
    cabeceras_analisis['XFO'] = cabeceras_upper.get('X-FRAME-OPTIONS', 'AUSENTE: Riesgo de Clickjacking').strip()
    cabeceras_analisis['HSTS'] = cabeceras_upper.get('STRICT-TRANSPORT-SECURITY', 'AUSENTE: Recomendado para HTTPS').strip()
    return cabeceras_analisis

# ----------------------------------------------------------------------
# RUTA PRINCIPAL (ANÁLISIS)
# ----------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def analizar_url():
    resultados = None
    if request.method == 'POST':
        url = request.form['url']
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status() 
            
            # --- DATOS NECESARIOS ---
            cabeceras_respuesta = dict(response.headers)
            html_completo = response.text
            soup = BeautifulSoup(html_completo, 'html.parser')
            titulo = soup.title.string if soup.title else 'No se encontró título'
            
            css_archivos = []
            js_archivos = []
            total_recursos_externos = 0
            recursos_fallidos = []
            url_base = urljoin(url, '/')
            
            # 1. Extracción de CSS y JS (sin cambios)
            for link in soup.find_all('link', rel='stylesheet'):
                path_css = link.get('href')
                if path_css:
                    total_recursos_externos += 1
                    contenido, url_absoluta, nombre_descarga, nombre_corto = obtener_contenido_recurso(url_base, path_css)
                    if contenido:
                        css_archivos.append({'url': url_absoluta, 'contenido': contenido.strip(), 'nombre_descarga': nombre_descarga, 'nombre_corto': nombre_corto, 'estado': 'OK'})
                    else:
                        recursos_fallidos.append({'url': url_absoluta, 'tipo': 'CSS'})

            for script in soup.find_all('script', src=True):
                path_js = script.get('src')
                if path_js:
                    total_recursos_externos += 1
                    contenido, url_absoluta, nombre_descarga, nombre_corto = obtener_contenido_recurso(url_base, path_js)
                    if contenido:
                        js_archivos.append({'url': url_absoluta, 'contenido': contenido.strip(), 'nombre_descarga': nombre_descarga, 'nombre_corto': nombre_corto, 'estado': 'OK'})
                    else:
                        recursos_fallidos.append({'url': url_absoluta, 'tipo': 'JS'})

            # 2. Ejecución de todas las funciones de análisis
            palabras_clave = contar_palabras_clave(soup)
            meta_datos = extraer_metadatos(soup) 
            estructura_encabezados = extraer_encabezados(soup)
            analisis_imagenes = analizar_imagenes(soup)
            contenido_inline = detectar_contenido_inline(soup)
            etiquetas_obsoletas = buscar_etiquetas_obsoletas(soup)
            analisis_seguridad_basica = analizar_seguridad_basica(css_archivos, js_archivos, recursos_fallidos)
            analisis_iframes = analizar_iframes(soup)
            analisis_cabeceras = analizar_cabeceras_seguridad(cabeceras_respuesta)
            analisis_tabnabbing = analizar_enlaces_tabnabbing(soup)

            # 3. Compilación de resultados
            resultados = {
                'titulo': titulo,
                'html_completo': html_completo.strip(),
                'css_archivos': css_archivos,
                'js_archivos': js_archivos,
                'palabras_clave': palabras_clave,
                'meta_datos': meta_datos,
                'estructura_encabezados': estructura_encabezados,
                'conteo_recursos_ok': len(css_archivos) + len(js_archivos),
                'total_recursos_ext': total_recursos_externos,
                'recursos_fallidos': recursos_fallidos,
                'analisis_imagenes': analisis_imagenes,
                'contenido_inline': contenido_inline,
                'etiquetas_obsoletas': etiquetas_obsoletas,
                'analisis_seguridad_basica': analisis_seguridad_basica, 
                'analisis_iframes': analisis_iframes, 
                'analisis_cabeceras': analisis_cabeceras, 
                'analisis_tabnabbing': analisis_tabnabbing,
            }

        except requests.exceptions.RequestException as e:
            resultados = {'error': f"Error al conectar con la URL. Asegúrate de que es correcta y accesible. Detalle: {e}"}
        except Exception as e:
            resultados = {'error': f"Ocurrió un error inesperado al procesar el análisis: {e}"}

    return render_template('index.html', resultados=resultados)

# ----------------------------------------------------------------------
# RUTA: API PARA EL ASISTENTE DE IA (¡CORRECCIÓN APLICADA!)
# ----------------------------------------------------------------------
@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"response": "**Error de Configuración (503):** La clave API de Gemini no está configurada. El asistente no está disponible."}), 503

    data = request.json
    pregunta_usuario = data.get('question', '')
    resultados_analisis = data.get('analysis_data', {})
    
    if not pregunta_usuario:
        return jsonify({"response": "Por favor, ingresa una pregunta para el asistente."}), 400

    try:
        datos_analisis_texto = json.dumps(resultados_analisis, indent=2, ensure_ascii=False)
        
        full_prompt = f"""
        Eres un experto en SEO y desarrollo web, tu trabajo es dar consejos concisos basados
        en los datos del análisis que se te proporcionan. Responde siempre en español.
        
        DATOS DEL ANÁLISIS WEB:
        ---
        {datos_analisis_texto}
        ---
        
        PREGUNTA DEL USUARIO: {pregunta_usuario}
        
        Genera una respuesta clara, concisa y profesional.
        """
        
        # 🚨 CORRECCIÓN: Se elimina el campo "config" que causaba el error 400.
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}]
        }
        
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={
                'Content-Type': 'application/json',
                'X-goog-api-key': api_key 
            },
            json=payload,
            timeout=15 
        )
        response.raise_for_status()

        gemini_data = response.json()
        
        ai_response_text = gemini_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')
        
        if ai_response_text:
            return jsonify({"response": ai_response_text})
        else:
            feedback = gemini_data.get('promptFeedback', 'Desconocida')
            return jsonify({"response": f"**Error de la IA (No Response):** La IA no pudo generar una respuesta. Razón: {json.dumps(feedback, indent=2)}"}), 500
        
    except requests.exceptions.HTTPError as e:
        error_status_code = e.response.status_code if e.response is not None else 500
        error_detail = f"Error HTTP {error_status_code}."
        
        api_error_message = 'No hay mensaje detallado de Google.'
        try:
            api_error_message = e.response.json().get('error', {}).get('message', api_error_message)
        except:
             pass 

        if error_status_code in [401, 403]:
            error_detail += " **(AUTENTICACIÓN FALLIDA - Revisa tu clave API)**."
        elif error_status_code == 429:
            error_detail += " **(Límite de cuota excedido)**."

        error_detail += f" Mensaje de Google: {api_error_message}"
        
        return jsonify({"response": f"**Error de la API de Gemini:** {error_detail}"}), 500
        
    except Exception as e:
        return jsonify({"response": f"**Error Interno del Servidor/Conexión (Flask):** {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')