from fastapi import APIRouter, File, UploadFile
from typing import Union
import logging
import openai

from ...models.responses_csf import CSF
from ...services.orchestators import procesar_constancia

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/extraer_datos",
    response_model=Union[CSF.ResultadoConsolidado, CSF.ErrorRespuesta],
    summary="Extrae datos de una Constancia de Situación Fiscal."
)
async def procesar_csf_api(
    archivo_csf: UploadFile = File(...)
):
    """
    Sube un archivo PDF de una Constancia de Situación Fiscal.
    El sistema intentará extraer los datos usando Regex como método principal.
    Si falla, utilizará un modelo de IA como respaldo.
    """
    if not archivo_csf:
            return CSF.ErrorRespuesta(error="No se proporcionó ningún archivo.")
    try:
        resultado = await procesar_constancia(archivo_csf)
        
        return resultado


    ## Manejo de errores globales
    except openai.AuthenticationError:
        # Error específico si la API Key es incorrecta
        return CSF.ErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    
    except openai.APIConnectionError:
        # Error específico si no se puede conectar a la API
        return CSF.ErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    
    except Exception as e:
        # Error genérico para cualquier otro fallo inesperado y fatal
        logger.error(f"Error global inesperado: {e}")
        return CSF.ErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")