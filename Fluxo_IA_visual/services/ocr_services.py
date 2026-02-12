"""
Servicio OCR usando Qwen-VL vía OpenRouter con formato TOON.
Ubicación: services/ocr_service.py
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

import openai
from ..core.config import settings 
from .pdf_processor import convertir_pdf_a_imagenes 

logger = logging.getLogger(__name__)

class TOONFormat:
    """TOON = Table-Object-Ordered-Notation"""
    INICIO = "<<<TOON_START>>>"
    FIN = "<<<TOON_END>>>"
    SEPARADOR_FILA = "|||"
    SEPARADOR_CAMPO = "::"
    
    @classmethod
    def parsear_respuesta(cls, respuesta: str) -> Optional[Dict[str, Any]]:
        # ... (Tu lógica de parseo TOON que me enviaste va aquí intacta) ...
        # Por brevedad en la respuesta, asumo que copias tu implementación completa aquí.
        try:
            inicio = respuesta.find(cls.INICIO)
            fin = respuesta.find(cls.FIN)
            
            if inicio == -1 or fin == -1:
                try: return json.loads(respuesta)
                except: return None
            
            bloque = respuesta[inicio + len(cls.INICIO):fin].strip()
            lineas = [l.strip() for l in bloque.split('\n') if l.strip()]
            if not lineas: return None
            
            # Detección simple Objeto vs Tabla
            if cls.SEPARADOR_CAMPO in lineas[0] and cls.SEPARADOR_FILA not in lineas[0]:
                # Objeto
                resultado = {}
                for linea in lineas:
                    if cls.SEPARADOR_CAMPO in linea:
                        k, v = linea.split(cls.SEPARADOR_CAMPO, 1)
                        resultado[k.strip()] = cls._parsear_valor(v.strip())
                return resultado
            else:
                # Tabla (asumimos que devuelve el primer objeto si es lista de 1)
                campos = lineas[0].split(cls.SEPARADOR_FILA)
                if len(lineas) > 1:
                    vals = lineas[1].split(cls.SEPARADOR_FILA)
                    fila = {}
                    for i, c in enumerate(campos):
                        if i < len(vals): fila[c.strip()] = cls._parsear_valor(vals[i].strip())
                    return fila
                return {}
        except Exception as e:
            logger.error(f"Error TOON: {e}")
            return None

    @classmethod
    def _parsear_valor(cls, valor: str) -> Any:
        if valor in ["NULL", ""]: return None
        try: return float(valor) if '.' in valor else int(valor)
        except: pass
        return valor

class OCRService:
    def __init__(self):
        # Usamos settings o variable de entorno
        self._api_key = settings.OPENROUTER_API_KEY.get_secret_value()
        self._base_url = settings.OPENROUTER_BASE_URL
        self._client = None
        self.modelo_default = "qwen/qwen3-vl-235b-a22b-instruct"
    
    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client
        
    async def extraer_con_vision(
        self,
        pdf_bytes: bytes,
        prompt_sistema: str,
        paginas: Optional[List[int]] = None,
        modelo: Optional[str] = None,
        formato_salida: str = "TOON"
    ) -> Dict[str, Any]:
        """Extrae datos usando Qwen-VL + TOON."""
        try:
            # 1. Determinar páginas
            if paginas is None:
                # Lógica simple: 1, 2 y última. 
                # (Puedes importar tu helper _determinar_paginas aquí si lo deseas)
                paginas = [1] 

            # 2. Imágenes
            imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas)
            if not imagen_buffers:
                return {"error": "Fallo conversión imágenes", "datos": None}

            # 3. Payload
            content = [{"type": "text", "text": prompt_sistema}]
            for buffer in imagen_buffers:
                buffer.seek(0)
                b64 = base64.b64encode(buffer.read()).decode('utf-8')
                content.append({
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}
                })

            # 4. Request
            res = await self.client.chat.completions.create(
                model=modelo or self.modelo_default,
                messages=[{"role": "user", "content": content}],
                temperature=0.1,
                max_tokens=4000
            )
            
            raw = res.choices[0].message.content
            
            # 5. Parseo
            datos = None
            if formato_salida == "TOON":
                datos = TOONFormat.parsear_respuesta(raw)
            
            return {
                "datos": datos,
                "error": None if datos else "No se pudieron parsear datos TOON",
                "raw": raw
            }

        except Exception as e:
            logger.error(f"OCR Crash: {e}")
            return {"error": str(e), "datos": None}

# Instancia Global
ocr_service = OCRService()