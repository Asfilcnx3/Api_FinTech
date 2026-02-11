# Aqui irán todas las funciones de extracción de PDF (sin IA)
from ..core.exceptions import PDFCifradoError
from ..utils.helpers_texto_fluxo import TRIGGERS_CONFIG, KEYWORDS_COLUMNAS

from typing import Dict, List, Optional, Tuple
from io import BytesIO
from pyzbar.pyzbar import decode
import fitz
import logging
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

def convertir_pdf_a_imagenes(pdf_bytes: bytes, paginas: List[int] = [1]) -> List[BytesIO]:
    buffers_imagenes = []
    matriz_escala = fitz.Matrix(2, 2)  # Aumentar resolución

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as documento:
            for num_pagina in paginas:
                if 0 <= num_pagina - 1 < len(documento):
                    pagina = documento.load_page(num_pagina - 1)
                    pix = pagina.get_pixmap(matrix=matriz_escala)
                    img_bytes = pix.tobytes("png")
                    buffers_imagenes.append(BytesIO(img_bytes))
                else:
                    logger.warning(f"Advertencia: Página {num_pagina} fuera de rango.")

    except Exception as e:
        # Lanza un error estándar que será atrapado y reportado por archivo
        raise ValueError(f"No se pudo procesar el archivo como PDF: {e}")

    return buffers_imagenes

def extraer_texto_con_crop(
    pdf_path: str, 
    paginas: List[int], 
    margen_superior_pct: float = 0.12, 
    margen_inferior_pct: float = 0.06
) -> Dict[int, str]:
    """
    Extrae texto aplicando un recorte geométrico Y ORDENAMIENTO VISUAL (Layout).
    """
    texto_limpio = {}
    
    try:
        with fitz.open(pdf_path) as doc:
            for num_pagina in paginas:
                idx = num_pagina - 1 
                
                if 0 <= idx < len(doc):
                    page = doc[idx]
                    rect_completo = page.rect
                    
                    y1 = rect_completo.height * margen_superior_pct
                    y2 = rect_completo.height * (1 - margen_inferior_pct)
                    
                    rect_recorte = fitz.Rect(0, y1, rect_completo.width, y2)
                    
                    # Usamos sort=True para que Fitz reorganice el texto visualmente (lectura humana)
                    # Esto es vital para que las columnas de montos no aparezcan antes que la descripción
                    texto_crop = page.get_text("text", clip=rect_recorte, sort=True)
                    
                    texto_limpio[num_pagina] = texto_crop.lower()
                    
    except Exception as e:
        logger.error(f"Error en crop geométrico para {pdf_path}: {e}")
        return {} 

    return texto_limpio

def leer_qr_de_imagenes(imagen_buffers: List[BytesIO]) -> Optional[str]:
    """
    Lee una lista de imágenes en memoria y devuelve el contenido del primer QR que encuentre.
    """
    for buffer in imagen_buffers:
        # Reiniciamos el puntero del buffer para que PIL pueda leerlo
        buffer.seek(0)
        imagen = Image.open(buffer)

        # 'decode' busca todos los códigos de barras/QR en la imagen
        codigos_encontrados = decode(imagen)

        if codigos_encontrados:
            # Devolvemos el dato del primer código encontrado, decodificado a string
            primer_codigo = codigos_encontrados[0].data.decode("utf-8")
            return primer_codigo

    logger.error("No se encontró ningún código QR en las imágenes.")
    return None # No se encontró ningún QR en ninguna imagen

# Estas funciones hacen el trabajo pesado para UN SOLO PDF.
# --- FUNCIÓN PARA EXTRACCIÓN DE TEXTO CON OCR ---

def extraer_texto_con_ocr(pdf_bytes: bytes, dpi: int = 300) -> str:
    """
    Realiza OCR en todas las páginas de un PDF (dado en bytes) y devuelve el texto concatenado.
    """
    textos_de_paginas = []
    try:
        doc_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")

        for pagina in doc_pdf:
            pix = pagina.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            imagen_pil = Image.open(BytesIO(img_bytes))

            texto_pagina = pytesseract.image_to_string(imagen_pil)
            textos_de_paginas.append(texto_pagina.lower())

        doc_pdf.close()
        return "\n".join(textos_de_paginas)
    except Exception as e:
        return f"ERROR_OCR: {e}" 
    
# --- FUNCIÓN PARA LA EXTRACCIÓN DE TEXTO CON FITZ SIN OCR ---
def extraer_texto_de_pdf(pdf_bytes: bytes, num_paginas: Optional[int] = None) -> str:
    """
    Extrae texto de un archivo PDF desde memoria (bytes) usando PyMuPDF (fitz).
    Convierte todo a minúsculas. Usa `with` para liberar memoria automáticamente.

    - Si `num_paginas` es None (por defecto), extrae todas las páginas.
    - Si `num_paginas` es un int (ej. 2), extrae las primeras 'n' páginas.
    - Lanza PDFCifradoError si el documento está protegido con contraseña.
    - Lanza RuntimeError para otros errores de extracción.

    Args:
        pdf_bytes (bytes): Contenido del PDF en bytes.

    Returns:
        str: Texto extraído en minúsculas (normalizado).
    """
    texto_extraido = ''

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            # 1. Verificación e Contraseña (se hace una sola vez)
            if doc.is_encrypted: # Si el documento está con contraseña arrojamos un error
                raise PDFCifradoError("El documento está protegido por contraseña.")
            
            # 2. Determinar el rango de páginas a procesar
            paginas_a_iterar = doc
            if num_paginas is not None and num_paginas > 0:
                # Crea un iterador solo para las primeras 'n' páginas
                paginas_a_iterar = list(doc.pages())[:num_paginas]

            # 3. Extraer el texto del rango de páginas seleccionado
            for pagina in paginas_a_iterar:
                texto_pagina = pagina.get_text(sort=True)
                if texto_pagina:
                    texto_extraido += texto_pagina.lower() + '\n'

    except PDFCifradoError:
        # Si es un error de contraseña, lo relanzamos para que la API lo maneje
        raise
    except Exception as e:
        # Para cualquier otro error, lanzamos un error genérico
        logger.warning(f"Error durante la extracción de texto con fitz: {e}")
        raise RuntimeError(f"No se pudo leer el contenido del PDF: {e}") from e
        
    return texto_extraido

# --- FUNCIÓN PARA EXTRAER MOVIMIENTOS CON POSICIONES ---
def detectar_rangos_y_texto(pdf_bytes: bytes) -> Tuple[Dict[int, str], List[Tuple[int, int]]]:
    """
    Escanea el PDF para extraer el texto crudo por página y detectar 
    dónde empiezan y terminan las cuentas (Rangos).
    YA NO EXTRAE MOVIMIENTOS (Eso lo hará la fase geométrica dedicada).
    """
    texto_por_pagina = {}
    rangos_detectados = []
    inicio_actual = None
    
    # Configuración de triggers (Asegúrate de tener TRIGGERS_CONFIG importado)
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total_paginas = len(doc)
            
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                page_text = page.get_text("text").lower()
                texto_por_pagina[page_num] = page_text
                
                # --- LÓGICA DE RANGOS (INTACTA) ---
                if inicio_actual is None:
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        inicio_actual = page_num

                if inicio_actual is not None:
                    encontrado_fin = False
                    # A. Fin explícito
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["fin"]):
                        rangos_detectados.append((inicio_actual, page_num))
                        inicio_actual = None
                        encontrado_fin = True
                    
                    # B. Nuevo inicio (Cascada)
                    elif page_num > inicio_actual and any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        rangos_detectados.append((inicio_actual, page_num - 1))
                        inicio_actual = page_num
                    
                    # C. Fin de documento
                    if not encontrado_fin and inicio_actual is not None and page_num == total_paginas:
                        rangos_detectados.append((inicio_actual, total_paginas))
                        inicio_actual = None

    except Exception as e:
        logger.error(f"Error detectando rangos: {e}")

    # Fallback si no hay rangos
    if not rangos_detectados:
        rangos_detectados = [(1, len(texto_por_pagina))]

    return texto_por_pagina, rangos_detectados

def detectar_zonas_columnas(page: fitz.Page) -> Dict[str, Tuple[float, float]]:
    """
    Escanea la página (priorizando el tercio superior) buscando encabezados 
    de columnas para definir las zonas X de 'cargo' y 'abono'.
    """
    # Asegúrate de importar esto arriba o dentro de la función para evitar ciclos
    from ..utils.helpers_texto_fluxo import KEYWORDS_COLUMNAS 
    
    # Inicializamos con fecha_columna (del código viejo) para mantener compatibilidad
    ancho_pag = page.rect.width
    zonas = {
        "cargo": None, 
        "abono": None, 
        "fecha_columna": (0, ancho_pag * 0.22) # Default seguro
    }
    
    # Limitamos la búsqueda al tercio superior para evitar falsos positivos en descripciones
    # (Del código nuevo: esto es vital)
    rect_header = fitz.Rect(0, 0, ancho_pag, page.rect.height * 0.35)
    words = page.get_text("words", clip=rect_header)
    
    # Lista para guardar candidatos encontrados: {x_centro, tipo}
    candidatos = []

    for w in words:
        # Limpieza robusta
        texto = w[4].lower().replace(":", "").replace(".", "").strip()
        x0, x1 = w[0], w[2]
        
        # Check Cargo
        if texto in KEYWORDS_COLUMNAS["cargo"]:
            candidatos.append({"tipo": "cargo", "x0": x0, "x1": x1, "y": w[1]})
            
        # Check Abono
        elif texto in KEYWORDS_COLUMNAS["abono"]:
            candidatos.append({"tipo": "abono", "x0": x0, "x1": x1, "y": w[1]})

    # Procesar candidatos: 
    # Margen de tolerancia horizontal (expandimos la columna detectada a los lados)
    margen_expansion = 25 # Un poco más generoso para atrapar números largos

    for c in candidatos:
        # Definimos la zona con holgura a los lados
        zona_tupla = (c["x0"] - margen_expansion, c["x1"] + margen_expansion)
        
        # Si ya tenemos una zona detectada, priorizamos la que esté más "arriba" (menor Y)
        # o simplemente nos quedamos con la primera encontrada confiable.
        if zonas[c["tipo"]] is None:
            zonas[c["tipo"]] = zona_tupla

    # --- FALLBACK DE EMERGENCIA (La magia de la v2) ---
    # Si detectamos una columna pero no la otra, inferimos la faltante por posición.
    centro_pag = ancho_pag / 2
    
    if zonas["cargo"] and not zonas["abono"]:
        # Si cargo está a la izquierda (lo normal), abono debe estar a la derecha
        if zonas["cargo"][1] < centro_pag: 
            zonas["abono"] = (centro_pag, ancho_pag) # Asumimos toda la mitad derecha
            
    elif zonas["abono"] and not zonas["cargo"]:
        # Si abono está a la derecha, cargo debe estar a la izquierda
        if zonas["abono"][0] > centro_pag: 
            zonas["cargo"] = (0, centro_pag) # Asumimos toda la mitad izquierda

    return zonas