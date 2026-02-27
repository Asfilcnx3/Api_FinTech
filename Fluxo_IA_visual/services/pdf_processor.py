from ..core.exceptions import PDFCifradoError
from ..utils.helpers_texto_fluxo import TRIGGERS_CONFIG

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