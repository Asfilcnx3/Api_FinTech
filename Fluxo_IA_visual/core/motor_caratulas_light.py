## Este módulo define un motor ligero específico para extraer solo la información de la carátula de los estados de cuenta bancarios, utilizando tu servicio OCR basado en Qwen-VL y el prompt TOON configurado en los helpers del frontend.
## La idea es que este motor sea rápido y eficiente, enfocándose únicamente en las primeras páginas que contienen la información de la carátula, y devolviendo un modelo de datos simplificado para el frontend.

import logging

# Importamos el servicio OCR que ya sabe parsear TOON
from ..services.ocr_services import ocr_service

# Importamos el motor original solo para usar su detector de rangos
from .motor_caratulas import MotorCaratulas 
from ..models.responses_frontend import RespuestaCaratulasFrontend, DatosCaratulaLight

# Prompt TOON
from ..utils.helpers_texto_frontend import PROMPT_EXTRACCION_CARATULA_TOON

logger = logging.getLogger(__name__)

async def procesar_caratula_frontend(
    pdf_bytes: bytes, 
    motor_base: MotorCaratulas
) -> RespuestaCaratulasFrontend:
    """
    Orquestador ligero que extrae solo la primera cuenta de un PDF
    y devuelve banco, clabe y periodo para el frontend.
    """
    try:
        # 1. Usamos la inteligencia del motor base para sacar los rangos y el texto
        texto_por_pagina, rangos_cuentas = motor_base.extraer_texto_y_rangos(pdf_bytes)
        
        texto_global = "\n".join(texto_por_pagina.values())
        
        if not motor_base.validar_documento_digital(texto_global):
            logger.warning("El documento fue rechazado por el filtro de palabras clave (Regex).")
            return RespuestaCaratulasFrontend(
                error_procesamiento="El documento no parece ser un estado de cuenta bancario válido, está vacío o es un escaneo ilegible."
            )

        if not rangos_cuentas:
            return RespuestaCaratulasFrontend(
                error_procesamiento="No se encontraron cuentas o páginas válidas en el documento."
            )

        # 2. SOLO TOMAMOS EL PRIMER RANGO
        inicio_rango, fin_rango = rangos_cuentas[0]
        logger.info(f"Procesando solo el primer rango detectado: {inicio_rango} a {fin_rango}")

        # Definimos las páginas a enviar a la IA (Solo la portada de ese rango)
        paginas_para_ia = [inicio_rango]
        if (inicio_rango + 1) <= fin_rango:
            paginas_para_ia.append(inicio_rango + 1)

        # 3. Llamamos al servicio OCR (Qwen-VL) que ya se tiene configurado para TOON
        resultado_ocr = await ocr_service.extraer_con_vision(
            pdf_bytes=pdf_bytes,
            prompt_sistema=PROMPT_EXTRACCION_CARATULA_TOON,
            paginas=paginas_para_ia,
            formato_salida="TOON"
        )

        if resultado_ocr.get("error") or not resultado_ocr.get("datos"):
            error_msg = resultado_ocr.get("error", "La IA no devolvió datos válidos.")
            logger.error(f"Fallo en la extracción TOON: {error_msg}")
            return RespuestaCaratulasFrontend(error_procesamiento=error_msg)

        # 4. Parseamos y armamos la respuesta de la IA
        datos_extraidos = resultado_ocr["datos"]
        
        banco = str(datos_extraidos.get("banco", "")).lower().strip() if datos_extraidos.get("banco") else None
        clabe_raw = str(datos_extraidos.get("clabe", "")).strip() if datos_extraidos.get("clabe") else None
        periodo = str(datos_extraidos.get("periodo", "")).strip() if datos_extraidos.get("periodo") else None

        # --- CORRECCIÓN ESTRICTA DE CLABE ---
        clabe = None
        if clabe_raw and clabe_raw.lower() != "null":
            # 1. Eliminamos cualquier basura no numérica (espacios, guiones que la IA haya colado)
            clabe_numeros = ''.join(filter(str.isdigit, clabe_raw))
            
            # 2. Rellenamos con ceros a la izquierda hasta garantizar los 18 dígitos
            if clabe_numeros:
                clabe = clabe_numeros.zfill(18)

        # Si el modelo contestó "NULL" textual para los otros campos, lo limpiamos
        if banco == "null": banco = None
        if periodo == "null": periodo = None

        # --- NUEVO: VALIDACIÓN DE RFC Y CLABE ---
        # A. Extraemos el texto específico del rango que procesamos
        textos_del_rango = [texto_por_pagina.get(p, "") for p in range(inicio_rango, fin_rango + 1)]
        texto_rango_str = "\n".join(textos_del_rango).lower()

        # B. Usamos la extracción estática (Regex) rápida para buscar el RFC
        datos_estaticos = motor_base.identificar_banco_y_datos_estaticos(texto_rango_str)
        rfc_estatico = datos_estaticos.get("rfc")

        # C. Armamos un diccionario temporal para la validación
        datos_para_validar = {
            "rfc": rfc_estatico,
            "clabe_interbancaria": clabe
        }

        # D. Pasamos por el filtro estricto
        if not motor_base._es_cuenta_valida(datos_para_validar, texto_rango_str):
            logger.warning(f"La cuenta no pasó el filtro de validación (Falta CLABE válida o el RFC no coincide).")
            return RespuestaCaratulasFrontend(
                error_procesamiento="El documento parece ser un estado de cuenta, pero no se encontró una CLABE válida o el RFC es incorrecto/pertenece a un banco excluido."
            )
        # ----------------------------------------

        # 5. Si todo es válido, construimos el modelo final
        caratula_light = DatosCaratulaLight(
            banco=banco,
            clabe=clabe,
            periodo=periodo
        )

        return RespuestaCaratulasFrontend(resultados=[caratula_light])

    except Exception as e:
        logger.error(f"Error fatal en orquestador ligero de carátulas: {e}")
        return RespuestaCaratulasFrontend(error_procesamiento=f"Error interno del servidor: {str(e)}")