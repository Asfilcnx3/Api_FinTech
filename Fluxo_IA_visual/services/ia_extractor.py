from .pdf_processor import convertir_pdf_a_imagenes
from ..core.config import settings
from ..utils.helpers import _crear_prompt_agente_unificado, parsear_respuesta_toon

from fastapi import HTTPException
from openai import AsyncOpenAI
from typing import List, Dict, Any
from io import BytesIO
import json
import re
import base64
import logging

nomi_api = settings.OPENAI_API_KEY_NOMI.get_secret_value()

def get_fluxo_client():
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY_FLUXO.get_secret_value())

openrouter_api = settings.OPENROUTER_API_KEY.get_secret_value()

logger = logging.getLogger(__name__)

client_gpt_nomi = AsyncOpenAI(
    api_key=nomi_api
)


client_openrouter = AsyncOpenAI(
    api_key=openrouter_api,
    base_url=settings.OPENROUTER_BASE_URL,
    default_headers={
        "HTTP-Referer": "https://github.com/Asfilcnx3", 
        "X-Title": "Fluxo IA Test", 
    },
)
## ANALISIS DE FLUXO
# Función para enviar el prompt + imagen a GPT-5
async def analizar_gpt_fluxo(
        prompt: str, 
        pdf_bytes: bytes,
        paginas_a_procesar: List[int],
        razonamiento: str = "low", 
        detalle: str = "high"
    ) -> str:
    """
    Se hace la llamada al modelo GPT-5 con razonamiento bajo y detalle de imagen alto
    """
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": detalle
                },
            })
    client = get_fluxo_client()
    response = await client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "user","content": content}],
        reasoning_effort=razonamiento
    )

    return response.choices[0].message.content

# Función para enviar el prompt + imagen a modelo de preferencia
async def analizar_gemini_fluxo(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int]) -> str:
    """
    Se hace la llamada al modelo de preferencia
    """
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": "high"
                },
            })
    response = await client_openrouter.chat.completions.create(
        model="qwen/qwen3-vl-235b-a22b-instruct", # CAMBIAR AL MODELO QUE SE QUIERA USAR
        messages=[{"role": "user","content": content}],
    )

    return response.choices[0].message.content

async def llamar_agente_tpv(
    banco: str, 
    texto_chunk: str, 
    paginas: List[int]
) -> List[Dict[str, Any]]:
    """
    Llama a un agente LLM experto con un prompt de texto específico
    para extraer transacciones de un chunk de texto.
    """
    logger.info(f"Agente TPV: Procesando {banco} (Páginas: {paginas[0]}-{paginas[-1]})")

    # 1. Crear el prompt de sistema y de usuario
    prompt_sistema = _crear_prompt_agente_unificado(banco, tipo="texto")
    prompt_usuario = f"""
    Aquí está el fragmento de texto (páginas {paginas[0]} a {paginas[-1]}):
    
    ---INICIO DEL FRAGMENTO---
    {texto_chunk}
    ---FIN DEL FRAGMENTO---
    """

    try:
        # 2. Llamar al LLM (modo texto)
        client = get_fluxo_client()
        response = await client.chat.completions.create(
            model="gpt-5.2", # O tu modelo de texto preferido
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            # Si el modelo soporta JSON mode, es altamente recomendado:
            # response_format={"type": "json_object"} 
        )
        
        respuesta_str = response.choices[0].message.content

        if "SIN_DATOS" in respuesta_str:
            return []

        transacciones = parsear_respuesta_toon(respuesta_str)
        
        logger.debug(f"Agente TPV ({banco}): TOON parseado, {len(transacciones)} transacciones encontradas.")
        return transacciones
        
    except Exception as e:
        logger.error(f"Error crítico llamando al Agente TPV para {banco} (págs {paginas[0]}-{paginas[-1]}): {e}", exc_info=True)
        return [] # Devuelve lista vacía en caso de cualquier error

## ANALISIS DE NOMIFLASH
async def analizar_gpt_nomi(
        prompt: str, 
        imagen_buffers: List[BytesIO], 
        razonamiento: str = "low", 
        detalle: str = "high"
    ) -> str:
    if not imagen_buffers:
        return None

    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        buffer.seek(0)
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded_image}", "detail": detalle}
        })
    try:
        response = await client_gpt_nomi.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": content}],
            reasoning_effort=razonamiento
        )
        return response.choices[0].message.content  
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"El servicio de IA no está disponible: {e}")

async def llamar_agente_ocr_vision(
        banco: str, 
        pdf_bytes: bytes, 
        paginas: List[int] 
    ) -> List[Dict[str, Any]]: 
    """ Llama a un agente LLM multimodal (Qwen-VL) con las imágenes de las páginas de un PDF para extraer transacciones. """ 
    logger.info(f"Agente OCR-Visión: Procesando {banco} (Páginas: {paginas[0]}-{paginas[-1]})")

    # 1. Crear el prompt de texto
    prompt_sistema_texto = _crear_prompt_agente_unificado(banco, tipo="vision")

    # 2. Convertir las páginas de este chunk a imágenes
    # (Reutilizamos la función que ya tenías para el análisis de portada)
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas)
    if not imagen_buffers:
        logger.warning(f"No se pudieron generar imágenes para las páginas {paginas} de {banco}")
        return []

    # 3. Construir el payload multimodal (texto + imágenes)
    content = [{"type": "text", "text": prompt_sistema_texto}]
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": "high" # 'high' es crucial para que el OCR lea el texto
            },
        })

    try:
        # 4. Llamar al modelo Qwen-VL vía OpenRouter
        response = await client_openrouter.chat.completions.create(
            model="qwen/qwen3-vl-235b-a22b-instruct", # Tu modelo de OpenRouter
            messages=[{"role": "user", "content": content}],
            temperature=0.1, # Casi 0 para máxima consistencia
            max_tokens=4000, # Asegurar espacio para JSONs largos
        )

        respuesta_str = response.choices[0].message.content
        logger.debug(f"Agente OCR ({banco}) RAW TOON: {respuesta_str[:100]}...") # Loguear inicio para ver formato

        # --- PARSEO TOON ---
        if "SIN_DATOS" in respuesta_str:
            return []

        transacciones = parsear_respuesta_toon(respuesta_str)
        
        logger.debug(f"Agente OCR ({banco}): TOON parseado, {len(transacciones)} transacciones encontradas.")
        return transacciones

    except Exception as e:
        logger.error(f"Error crítico llamando al Agente OCR-Visión para {banco}: {e}", exc_info=True)
        return []

async def _extraer_datos_con_ia(texto: str) -> Dict:
    """
    Función de fallback que usa la IA para extraer los datos si la regex falla.
    """
    prompt_ia = f"""
    Extrae los datos de la siguiente Constancia de Situación Fiscal.
    Devuelve únicamente un JSON con las secciones: 'identificacion_contribuyente', 'domicilio_registrado'.
    Texto a analizar:
    ---
    {texto[:4000]}
    """
    try:
        client = get_fluxo_client()
        response = await client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt_ia}],
            # response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return e
