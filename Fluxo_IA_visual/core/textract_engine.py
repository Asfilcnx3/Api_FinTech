import concurrent.futures
from pdf2image import convert_from_path
import cv2
import boto3
import numpy as np
import re
import logging
from .config import settings

logger = logging.getLogger(__name__)

def extraer_saldo_inicial_poc(filas_texto):
    rx_saldo = re.compile(r'SALDO\s+INICIAL.*?(?P<monto>\d{1,3}(?:,\d{3})*\.\d{2})', re.IGNORECASE)
    for fila in filas_texto:
        match = rx_saldo.search(fila)
        if match:
            monto_str = match.group("monto").replace(',', '')
            return float(monto_str)
    return 0.0

def limpiar_imagen_para_ocr(imagen_pil):
    img_np = np.array(imagen_pil)
    img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gris = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    limpia = cv2.adaptiveThreshold(
        gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15
    )
    kernel = np.ones((1, 1), np.uint8)
    limpia = cv2.morphologyEx(limpia, cv2.MORPH_CLOSE, kernel)
    return limpia

def inicializar_textract():
    return boto3.client(
        'textract',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID.get_secret_value(),
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY.get_secret_value(),
        region_name=settings.AWS_REGION_TEXTRACT
    )

def extraer_texto_textract(textract_client, imagen_cv2):
    exito, buffer = cv2.imencode('.jpg', imagen_cv2)
    if not exito:
        raise ValueError("Error al codificar la imagen a JPG en memoria.")
    imagen_bytes = buffer.tobytes()
    return textract_client.detect_document_text(Document={'Bytes': imagen_bytes})

def parsear_y_ordenar_textract_estructurado(respuesta_aws, umbral_interseccion=0.4):
    lineas_extraidas = []
    for bloque in respuesta_aws.get('Blocks', []):
        if bloque['BlockType'] == 'LINE':
            geo = bloque['Geometry']['BoundingBox']
            lineas_extraidas.append({
                'texto': bloque['Text'],
                'confianza': bloque['Confidence'],
                'top': geo['Top'],
                'bottom': geo['Top'] + geo['Height'],
                'left': geo['Left']
            })
            
    lineas_extraidas.sort(key=lambda x: x['top'])
    filas_reconstruidas = []
    fila_actual = []
    banda_top = None
    banda_bottom = None
    
    for linea in lineas_extraidas:
        if not fila_actual:
            fila_actual.append(linea)
            banda_top = linea['top']
            banda_bottom = linea['bottom']
            continue
            
        overlap_top = max(banda_top, linea['top'])
        overlap_bottom = min(banda_bottom, linea['bottom'])
        overlap_height = max(0, overlap_bottom - overlap_top)
        altura_linea = linea['bottom'] - linea['top']
        
        if (overlap_height / altura_linea) >= umbral_interseccion:
            fila_actual.append(linea)
            banda_top = min(banda_top, linea['top'])
            banda_bottom = max(banda_bottom, linea['bottom'])
        else:
            fila_actual.sort(key=lambda x: x['left'])
            filas_reconstruidas.append({
                "texto_unido": " | ".join([item['texto'] for item in fila_actual]),
                "bloques": fila_actual
            })
            fila_actual = [linea]
            banda_top = linea['top']
            banda_bottom = linea['bottom']
            
    if fila_actual:
        fila_actual.sort(key=lambda x: x['left'])
        filas_reconstruidas.append({
            "texto_unido": " | ".join([item['texto'] for item in fila_actual]),
            "bloques": fila_actual
        })
        
    return filas_reconstruidas

def procesar_pagina_worker(num_pagina, imagen_pil):
    try:
        img_procesada = limpiar_imagen_para_ocr(imagen_pil)
        cliente_aws = inicializar_textract()
        respuesta_cruda = extraer_texto_textract(cliente_aws, img_procesada)
        filas_data = parsear_y_ordenar_textract_estructurado(respuesta_cruda)
        return {"pagina": num_pagina, "exito": True, "filas_data": filas_data, "error": None}
    except Exception as e:
        return {"pagina": num_pagina, "exito": False, "filas_data": [], "error": str(e)}

def extraer_documento_completo(ruta_pdf):
    logger.info(f"Cargando {ruta_pdf} en memoria para Textract...")
    
    # Preparamos los argumentos base
    kwargs_poppler = {"dpi": 300}
    
    # Si la variable de entorno tiene una ruta (Windows), la inyectamos
    if settings.POPPLER_PATH:
        kwargs_poppler["poppler_path"] = settings.POPPLER_PATH
        logger.info(f"Usando binarios locales de Poppler en: {settings.POPPLER_PATH}")
        
    imagenes_pil = convert_from_path(ruta_pdf, **kwargs_poppler)
    logger.info(f"PDF cargado. {len(imagenes_pil)} páginas listas para Textract.")

    resultados_globales = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futuros = {
            executor.submit(procesar_pagina_worker, i + 1, img): i + 1 
            for i, img in enumerate(imagenes_pil)
        }
        
        for futuro in concurrent.futures.as_completed(futuros):
            num_pag = futuros[futuro]
            try:
                resultado = futuro.result()
                resultados_globales.append(resultado)
                if not resultado["exito"]:
                    logger.warning(f"[FAIL] Textract Página {num_pag} falló: {resultado['error']}")
            except Exception as exc:
                logger.error(f"[FATAL] Textract Página {num_pag} generó excepción: {exc}")

    resultados_globales.sort(key=lambda x: x["pagina"])
    
    filas_estructuradas_totales = []
    textos_unidos_totales = []
    
    for res in resultados_globales:
        for fila in res["filas_data"]:
            textos_unidos_totales.append(fila["texto_unido"])
            filas_estructuradas_totales.append(fila)
            
    return filas_estructuradas_totales, textos_unidos_totales