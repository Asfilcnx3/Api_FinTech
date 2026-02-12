import asyncio
import logging
from typing import Dict, Any, Type, Optional
from fastapi import UploadFile
from io import BytesIO
import fitz 

# Modelos
from ..models.responses_nomiflash import NomiFlash
from pydantic import BaseModel

# Helpers y Servicios
from ..services.pdf_processor import convertir_pdf_a_imagenes, extraer_texto_de_pdf, leer_qr_de_imagenes
from ..utils.helpers import extraer_json_del_markdown, sanitizar_datos_ia, extraer_rfc_curp_por_texto
from ..services.ia_extractor import analizar_gpt_nomi
from ..services.ocr_services import ocr_service

# Prompts
from ..utils.helpers_texto_nomi import (
    # Prompts para GPT Vision
    PROMPT_NOMINA, SEGUNDO_PROMPT_NOMINA, PROMPT_ESTADO_CUENTA, PROMPT_COMPROBANTE
)

from ..utils.prompts_toon import (
    # Prompts para OCR (TOON Format)
    PROMPT_TOON_NOMINA, PROMPT_TOON_NOMINA_SEGUNDA, PROMPT_TOON_ESTADO, PROMPT_TOON_COMPROBANTE
)

logger = logging.getLogger(__name__)

class NomiFlashEngine:
    """
    Motor centralizado con Fallback de 3 Niveles:
    1. Regex/QR (Determinista)
    2. GPT-5.2 Vision (Primario)
    3. Qwen-VL OCR + TOON (Secundario/Fallback)
    """

    # --- FACHADA PÚBLICA ---

    async def procesar_nomina(self, archivo: UploadFile) -> NomiFlash.RespuestaNomina:
        return await self._procesar_generico(
            archivo, 
            prompt_gpt=PROMPT_NOMINA, 
            prompt_toon=PROMPT_TOON_NOMINA,
            modelo_respuesta=NomiFlash.RespuestaNomina, 
            tipo_doc="nomina"
        )

    async def procesar_segunda_nomina(self, archivo: UploadFile) -> NomiFlash.SegundaRespuestaNomina:
        return await self._procesar_generico(
            archivo, 
            prompt_gpt=SEGUNDO_PROMPT_NOMINA, 
            prompt_toon=PROMPT_TOON_NOMINA_SEGUNDA,
            modelo_respuesta=NomiFlash.SegundaRespuestaNomina, 
            tipo_doc="segunda_nomina"
        )

    async def procesar_estado_cuenta(self, archivo: UploadFile) -> NomiFlash.RespuestaEstado:
        return await self._procesar_generico(
            archivo, 
            prompt_gpt=PROMPT_ESTADO_CUENTA, 
            prompt_toon=PROMPT_TOON_ESTADO,
            modelo_respuesta=NomiFlash.RespuestaEstado, 
            tipo_doc="estado"
        )

    async def procesar_comprobante(self, archivo: UploadFile) -> NomiFlash.RespuestaComprobante:
        return await self._procesar_generico(
            archivo, 
            prompt_gpt=PROMPT_COMPROBANTE, 
            prompt_toon=PROMPT_TOON_COMPROBANTE,
            modelo_respuesta=NomiFlash.RespuestaComprobante, 
            tipo_doc="comprobante"
        )

    # --- LÓGICA CORE ---

    async def _procesar_generico(
        self, 
        archivo: UploadFile, 
        prompt_gpt: str, 
        prompt_toon: str,
        modelo_respuesta: Type[BaseModel],
        tipo_doc: str
    ) -> BaseModel:
        
        filename = archivo.filename
        logger.info(f"Iniciando motor para {tipo_doc}: {filename}")
        
        try:
            pdf_bytes = await archivo.read()
            
            # ====================================================
            # NIVEL 1: EXTRACCIÓN DETERMINISTA (Regex y QR)
            # ====================================================
            # Extracción de texto crudo para regex (Rápido y barato)
            texto_inicial = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)
            tipo_regex = "nomina" if "nomina" in tipo_doc else tipo_doc
            rfc_regex, curp_regex = extraer_rfc_curp_por_texto(texto_inicial, tipo_regex)
            
            # Preparación de imágenes para IA
            loop = asyncio.get_running_loop()
            paginas = self._determinar_paginas_dinamicas(pdf_bytes, tipo_doc)
            
            imagen_buffers = await loop.run_in_executor(
                None, convertir_pdf_a_imagenes, pdf_bytes, paginas
            )
            
            # Lectura de QR (Muy fiable si existe)
            datos_qr = None
            if imagen_buffers:
                datos_qr = await loop.run_in_executor(None, leer_qr_de_imagenes, imagen_buffers)

            # ====================================================
            # NIVEL 2: IA PRIMARIA (GPT Vision)
            # ====================================================
            datos_finales = {}
            exito_primario = False

            if imagen_buffers:
                try:
                    # Llamada a tu servicio existente de GPT
                    respuesta_gpt = await analizar_gpt_nomi(prompt_gpt, imagen_buffers)
                    datos_crudos = extraer_json_del_markdown(respuesta_gpt)
                    datos_finales = sanitizar_datos_ia(datos_crudos)
                    
                    # Validamos si la IA trajo lo necesario
                    if self._validar_calidad_datos(datos_finales, tipo_doc):
                        exito_primario = True
                    else:
                        logger.warning(f"Calidad baja en GPT para {filename}. Activando Fallback...")

                except Exception as e:
                    logger.error(f"Fallo en GPT para {filename}: {e}")

            # ====================================================
            # NIVEL 3: FALLBACK OCR (Qwen-VL + TOON)
            # ====================================================
            if not exito_primario:
                logger.info(f"Ejecutando Fallback OCR (TOON) para {filename}...")
                
                resultado_ocr = await ocr_service.extraer_con_vision(
                    pdf_bytes=pdf_bytes,
                    prompt_sistema=prompt_toon,
                    paginas=paginas,
                    formato_salida="TOON"
                )
                
                if not resultado_ocr.get("error") and resultado_ocr.get("datos"):
                    # Si el OCR trajo datos, usamos esos (o hacemos merge inteligente)
                    datos_ocr = sanitizar_datos_ia(resultado_ocr["datos"])
                    
                    # Merge: Preferimos datos OCR si GPT falló, pero mantenemos lo que GPT sí encontró
                    # (En este caso simple, sobrescribimos con OCR porque asumimos que GPT falló)
                    datos_finales.update(datos_ocr)
                    logger.info(f"Datos recuperados exitosamente con OCR TOON.")
                else:
                    logger.error(f"Fallo total: Ni GPT ni OCR pudieron leer {filename}.")

            # ====================================================
            # FUSIÓN FINAL: La verdad absoluta (Regex/QR) manda
            # ====================================================
            if datos_qr: datos_finales["datos_qr"] = datos_qr
            if rfc_regex: datos_finales["rfc"] = rfc_regex[-1]
            if curp_regex: datos_finales["curp"] = curp_regex[-1]

            return modelo_respuesta(**datos_finales)

        except Exception as e:
            logger.error(f"Error fatal en motor para {filename}: {e}")
            # Mapeo del campo de error según el modelo
            campo_err = f"error_lectura_{'nomina' if 'nomina' in tipo_doc else tipo_doc}"
            return modelo_respuesta(**{campo_err: str(e)})

    # --- HELPERS ---

    def _determinar_paginas_dinamicas(self, pdf_bytes: bytes, tipo_doc: str) -> list:
        # Solo Estados de Cuenta requieren análisis de 1ra, 2da y última
        if tipo_doc != "estado":
            return [1] # Nóminas y comprobantes suelen ser página 1
            
        try:
            with fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf") as doc:
                total = len(doc)
            return sorted(list(set([1, 2, total])))
        except:
            return [1, 2]

    def _validar_calidad_datos(self, datos: Dict, tipo_doc: str) -> bool:
        """Reglas simples para decidir si activamos el fallback."""
        if not datos: return False
        
        if "nomina" in tipo_doc:
            # Debe tener al menos nombre Y (salario O percepciones)
            has_money = bool(datos.get("salario_neto") or datos.get("total_percepciones"))
            return bool(datos.get("nombre")) and has_money
            
        if tipo_doc == "estado":
            # Debe tener cuenta/clabe/rfc
            return bool(datos.get("clabe") or datos.get("numero_cuenta") or datos.get("rfc"))
            
        if tipo_doc == "comprobante":
            return bool(datos.get("domicilio") or datos.get("inicio_periodo"))
            
        return True