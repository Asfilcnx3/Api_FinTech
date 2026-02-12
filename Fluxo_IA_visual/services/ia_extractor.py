from .pdf_processor import convertir_pdf_a_imagenes
from ..core.config import settings
from ..utils.helpers import _crear_prompt_agente_unificado, parsear_respuesta_toon
from ..utils.helpers_texto_fluxo import PROMPT_FASE_3_AUDITOR_TEMPLATE, PROMPT_GENERICO, PROMPTS_POR_BANCO

from fastapi import HTTPException
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from io import BytesIO
import json
import base64
import logging
import httpx

# --- CONFIGURACIÓN Y CLIENTES ---
logger = logging.getLogger(__name__)

# Configuración de Timeouts para evitar cuelgues en paralelismo masivo
HTTP_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# SINGLETONS DE CLIENTES (Para reutilizar conexiones TCP)
_fluxo_client_instance = None
_openrouter_client_instance = None
_nomi_client_instance = None

def get_fluxo_client():
    """Retorna una instancia única del cliente Fluxo (OpenAI)."""
    global _fluxo_client_instance
    if _fluxo_client_instance is None:
        _fluxo_client_instance = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY_FLUXO.get_secret_value(),
            timeout=HTTP_TIMEOUT
        )
    return _fluxo_client_instance

def get_openrouter_client():
    """Retorna una instancia única del cliente OpenRouter."""
    global _openrouter_client_instance
    if _openrouter_client_instance is None:
        _openrouter_client_instance = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY.get_secret_value(),
            base_url=settings.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/Asfilcnx3", 
                "X-Title": "Fluxo IA Test", 
            },
            timeout=HTTP_TIMEOUT
        )
    return _openrouter_client_instance

def get_nomi_client():
    global _nomi_client_instance
    if _nomi_client_instance is None:
        _nomi_client_instance = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY_NOMI.get_secret_value(),
            timeout=HTTP_TIMEOUT
        )
    return _nomi_client_instance

# --- FUNCIONES DE CLASIFICACIÓN (FLUXO) ---

async def clasificar_lote_con_ia(
    banco: str, 
    transacciones: List[Any], 
    client: AsyncOpenAI = None # Inyección de dependencia opcional
) -> Dict[str, str]:
    """
    Fase 3: Envía un lote de descripciones a la IA para clasificación.
    Optimizado para alto rendimiento y bajo consumo de tokens.
    """
    if not transacciones:
        return {}

    # 1. Preparar Payload (Minimizado)
    # Solo enviamos ID, Desc y Monto. Fecha y Tipo no son necesarios para categorizar.
    payload_input = []
    for idx, tx in enumerate(transacciones):
        # Manejo híbrido (Dict o Objeto Pydantic)
        if isinstance(tx, dict):
            desc = tx.get("descripcion", "")
            monto = tx.get("monto", "0")
        else: 
            desc = getattr(tx, "descripcion", "")
            monto = getattr(tx, "monto", "0")

        payload_input.append({
            "id": idx, 
            "d": desc,
            "m": monto
        })
    
    # 2. Seleccionar Prompt
    banco_key = banco.lower().strip() if banco else "generico"
    reglas_a_usar = PROMPTS_POR_BANCO.get(banco_key, PROMPT_GENERICO)
    
    prompt_sistema = PROMPT_FASE_3_AUDITOR_TEMPLATE.format(
        banco=banco, 
        reglas_especificas=reglas_a_usar
    )
    
    # JSON dump compacto (separadores sin espacios)
    prompt_usuario = json.dumps(payload_input, separators=(',', ':'))

    try:
        # Usamos el cliente inyectado o el singleton
        ai_client = client or get_fluxo_client()
        
        response = await ai_client.chat.completions.create(
            model="gpt-5.2", # Asegúrate que este modelo exista o usa gpt-4o-mini / gpt-3.5-turbo
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        if not content: return {}
        
        return json.loads(content)

    except Exception as e:
        logger.error(f"Error IA ({banco}): {e}")
        # Fallback silencioso: todo es GENERAL si falla
        return {str(i): "GENERAL" for i in range(len(transacciones))}

async def llamar_agente_ocr_vision(banco: str, pdf_bytes: bytes, paginas: List[int]) -> List[Dict[str, Any]]:
    """Agente Multimodal OCR (Qwen-VL)."""
    logger.info(f"Agente OCR: {banco} (Págs {paginas})")
    
    prompt = _crear_prompt_agente_unificado(banco, tipo="vision")
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas)
    if not imagen_buffers: return []

    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        b64 = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}})

    try:
        client = get_openrouter_client()
        res = await client.chat.completions.create(
            model="qwen/qwen3-vl-235b-a22b-instruct",
            messages=[{"role": "user", "content": content}]
        )
        return parsear_respuesta_toon(res.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error Agente OCR {banco}: {e}")
        return []
    
# --- FUNCIONES DE ANALISIS DE PORTADA Y OCR (OPENROUTER/GPT-V) ---

async def analizar_gpt_fluxo(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int], razonamiento: str = "low", detail: str = "high") -> str:
    """Envía PDF a GPT-Vision (Fluxo)."""
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas_a_procesar)
    if not imagen_buffers: return ""
    
    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        b64 = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": detail}})
    
    client = get_fluxo_client()
    res = await client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "user", "content": content}],
        reasoning_effort=razonamiento
    )
    return res.choices[0].message.content

async def analizar_gemini_fluxo(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int]) -> str:
    """Envía PDF a OpenRouter (Gemini/Qwen)."""
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas_a_procesar)
    if not imagen_buffers: return ""
    
    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        b64 = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}})
    
    client = get_openrouter_client()
    res = await client.chat.completions.create(
        model="qwen/qwen3-vl-235b-a22b-instruct",
        messages=[{"role": "user", "content": content}],
    )
    return res.choices[0].message.content

# --- FUNCIONES LEGACY / TEXTO [[EN SU MAYORÍA SON USADAS DENTRO DEL FALLBACK PARA NOMIFLASH]] ---
async def _extraer_datos_con_ia(texto: str) -> Dict:
    """Extractor genérico de Constancia Fiscal."""
    prompt = f"Extrae JSON ('identificacion_contribuyente', 'domicilio_registrado') de:\n{texto[:4000]}"
    try:
        client = get_fluxo_client()
        res = await client.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(res.choices[0].message.content)
    except Exception:
        return {}

# --- FUNCIONES NOMI ---
async def analizar_gpt_nomi(prompt: str, imagen_buffers: List[BytesIO], razonamiento="low", detalle="high") -> str:
    if not imagen_buffers: return None
    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        buffer.seek(0)
        b64 = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": detalle}})
    
    client = get_nomi_client()
    res = await client.chat.completions.create(
        model="gpt-5.2",
        messages=[{"role": "user", "content": content}],
        reasoning_effort=razonamiento
    )
    return res.choices[0].message.content