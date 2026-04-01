## Este módulo define un motor ligero específico para extraer solo la información de la carátula de los estados de cuenta bancarios, utilizando tu servicio OCR basado en Qwen-VL y el prompt TOON configurado en los helpers del frontend.
## La idea es que este motor sea rápido y eficiente, enfocándose únicamente en las primeras páginas que contienen la información de la carátula, y devolviendo un modelo de datos simplificado para el frontend.

import logging

# Importamos el servicio OCR que ya sabe parsear TOON
from ..services.ocr_services import ocr_service

# Importamos el motor original solo para usar su detector de rangos
from .motor_caratulas import MotorCaratulas 
from ..models.responses_frontend import RespuestaCaratulasFrontend, DatosCaratulaLight

# Prompt TOON
from ..utils.helpers_texto_frontend import PROMPT_EXTRACCION_CARATULA_TOON, PROMPT_EXTRACCION_CARATULA_TOON_TEXTO
from ..services.ia_extractor import get_fluxo_client

logger = logging.getLogger(__name__)

async def procesar_caratula_frontend(
    pdf_bytes: bytes, 
    motor_base: MotorCaratulas,
    requiere_vision: bool = True # <--- Por defecto True por seguridad
) -> RespuestaCaratulasFrontend:
    """
    Orquestador ligero con enrutamiento inteligente (Texto vs Visión).
    """
    try:
        texto_por_pagina, rangos_cuentas = motor_base.extraer_texto_y_rangos(pdf_bytes)
        
        if not rangos_cuentas:
            return RespuestaCaratulasFrontend(error_procesamiento="No se encontraron cuentas o páginas válidas.")

        inicio_rango, fin_rango = rangos_cuentas[0]
        logger.info(f"Procesando primer rango: {inicio_rango} a {fin_rango}")

        paginas_para_ia = [inicio_rango]
        if (inicio_rango + 1) <= fin_rango:
            paginas_para_ia.append(inicio_rango + 1)

        datos_extraidos = {}

        if requiere_vision:
            logger.info("Enrutando a modelo OCR Multimodal (Qwen-VL) - $")
            resultado_ocr = await ocr_service.extraer_con_vision(
                pdf_bytes=pdf_bytes,
                prompt_sistema=PROMPT_EXTRACCION_CARATULA_TOON,
                paginas=paginas_para_ia,
                formato_salida="TOON"
            )
            if resultado_ocr.get("error") or not resultado_ocr.get("datos"):
                return RespuestaCaratulasFrontend(error_procesamiento=resultado_ocr.get("error", "Falla en Visión."))
            datos_extraidos = resultado_ocr["datos"]

        else:
            logger.info("Enrutando a modelo LLM de Texto Puro (GPT) - ¢")
            # Extraemos el texto de las páginas que íbamos a mandar a visión
            textos_del_rango = [texto_por_pagina.get(p, "") for p in paginas_para_ia]
            texto_a_leer = "\n".join(textos_del_rango)
            
            prompt_final = PROMPT_EXTRACCION_CARATULA_TOON_TEXTO.format(texto_documento=texto_a_leer[:10000])
            
            try:
                client = get_fluxo_client()
                res = await client.chat.completions.create(
                    model="gpt-5.2", 
                    messages=[{"role": "user", "content": prompt_final}],
                    temperature=0.0 # Determinista
                )
                respuesta_texto = res.choices[0].message.content
                
                # Pequeño parser manual para TOON de texto
                for linea in respuesta_texto.split("\n"):
                    if "::" in linea:
                        clave, valor = linea.split("::", 1)
                        datos_extraidos[clave.strip().lower()] = valor.strip()
                        
                if not datos_extraidos:
                    return RespuestaCaratulasFrontend(error_procesamiento="El LLM de texto no devolvió el formato TOON.")
                    
            except Exception as e:
                logger.error(f"Falla en LLM Texto: {e}")
                return RespuestaCaratulasFrontend(error_procesamiento=f"Error en LLM de texto: {e}")

        # Parseamos y armamos la respuesta
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
                error_procesamiento="El documento parece ser un estado de cuenta, pero no se encontró una CLABE válida o el RFC es incorrecto/pertenece a un banco excluido. (Revisa que el PDF tenga una carátula clara o que la información no esté demasiado borrosa)."
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