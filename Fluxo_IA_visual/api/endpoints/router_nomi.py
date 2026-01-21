from fastapi import APIRouter, UploadFile, File
from typing import Union, Optional
import asyncio
import logging
import openai

from ...models.responses_nomiflash import NomiFlash
from ...utils.helpers import aplicar_reglas_de_negocio
from ...services.orchestators import (
    procesar_nomina, procesar_comprobante, procesar_estado_cuenta, procesar_segunda_nomina
)

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Endpoint 1: Extracción general ---
@router.post(
        "/extraer_datos",
        response_model=Union[NomiFlash.ResultadoConsolidado, NomiFlash.ErrorRespuesta],
        summary="Extrae datos de diferentes tipos de documentos."
)
async def procesar_documentos_consolidados(
    recibo_de_nomina: Optional[UploadFile] = File(None),
    segundo_recibo_de_nomina: Optional[UploadFile] = File(None),
    estado_de_cuenta: Optional[UploadFile] = File(None),
    comprobante_de_domicilio: Optional[UploadFile] = File(None)
):
    """
    Sube uno o más archivos PDF. El sistema procesa todos en paralelo y devuelve una lista de resultados.
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_lectura` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error 503.
    """
    try:
        tasks = []
        # 1. Creamos las tareas llamando a la función procesadora correcta para cada archivo
        if recibo_de_nomina:
            tasks.append(procesar_nomina(recibo_de_nomina))
        if segundo_recibo_de_nomina:
            tasks.append(procesar_segunda_nomina(segundo_recibo_de_nomina))
        if estado_de_cuenta:
            tasks.append(procesar_estado_cuenta(estado_de_cuenta))
        if comprobante_de_domicilio:
            tasks.append(procesar_comprobante(comprobante_de_domicilio))
        if not tasks:
            return NomiFlash.ResultadoConsolidado()

        # 2. Ejecutamos todas las tareas en paralelo
        resultados_parciales = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Consolidamos los resultados
        resultado_final = NomiFlash.ResultadoConsolidado()

        for res in resultados_parciales:
            if isinstance(res, Exception):
                # Si una tarea falló por completo, registramos el error
                error_msg = f"Una de las tareas de procesamiento falló: {str(res)}"
                print(error_msg)
                # Podríamos añadirlo a una lista de errores generales si el modelo lo permitiera
                continue

            # Asignamos el resultado a su campo correspondiente
            if isinstance(res, NomiFlash.RespuestaNomina):
                resultado_final.Nomina = res
            elif isinstance(res, NomiFlash.SegundaRespuestaNomina):
                resultado_final.SegundaNomina = res
            elif isinstance(res, NomiFlash.RespuestaEstado):
                resultado_final.Estado = res
            elif isinstance(res, NomiFlash.RespuestaComprobante):
                resultado_final.Comprobante = res

        # 4. APLICAMOS LAS REGLAS DE NEGOCIO A RFC, CURP Y FECHA
        # Llamamos a nuestra nueva función para que haga todo el trabajo.
        resultado_final = aplicar_reglas_de_negocio(resultado_final)

        return resultado_final

    ## Manejo de errores globales
    except openai.AuthenticationError:
        # Error específico si la API Key es incorrecta
        return NomiFlash.ErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    except openai.APIConnectionError:
        # Error específico si no se puede conectar a la API
        return NomiFlash.ErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    except Exception as e:
        # Error genérico para cualquier otro fallo inesperado y fatal
        print(f"Error global inesperado: {e}")
        return NomiFlash.ErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")

# --- Endpoint 2: Solo para Nóminas ---
@router.post(
    "/validar_nominas",
    response_model=Union[NomiFlash.ResultadoConsolidado, NomiFlash.ErrorRespuesta],
    summary="Extrae y valida datos de los recibos de nómina."
)
async def validar_nominas(
    recibo_de_nomina: Optional[UploadFile] = File(None),
    segundo_recibo_de_nomina: Optional[UploadFile] = File(None)
):
    """
    Sube el primer y/o segundo recibo de nómina (PDF). 
    El sistema procesa ambos en paralelo, extrae los datos y aplica
    reglas de negocio específicas de nómina (ej. validación de QR).
    """
    try:
        tasks = []

        # 1. Creamos las tareas solo para las nóminas
        if recibo_de_nomina:
            tasks.append(procesar_nomina(recibo_de_nomina))
        
        if segundo_recibo_de_nomina:
            tasks.append(procesar_segunda_nomina(segundo_recibo_de_nomina))

        if not tasks:
            # Si no se envió ningún archivo, devuelve un resultado vacío
            return NomiFlash.ResultadoConsolidado()

        # 2. Ejecutamos las tareas de nómina en paralelo
        resultados_parciales = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Consolidamos los resultados
        resultado_final = NomiFlash.ResultadoConsolidado()

        for res in resultados_parciales:
            if isinstance(res, Exception):
                error_msg = f"Una de las tareas de procesamiento de nómina falló: {str(res)}"
                print(error_msg)
                # Opcional: podrías añadir este error a un campo 'error_general' 
                # en el modelo si existiera
                continue

            # Asignamos el resultado a su campo correspondiente
            if isinstance(res, NomiFlash.RespuestaNomina):
                resultado_final.Nomina = res
            elif isinstance(res, NomiFlash.SegundaRespuestaNomina):
                resultado_final.SegundaNomina = res

        # 4. APLICAMOS LAS REGLAS DE NEGOCIO
        # La función 'aplicar_reglas_de_negocio' solo aplicará la regla 
        # 'el_qr_es_igual' ya que solo tiene datos de nómina.
        resultado_final = aplicar_reglas_de_negocio(resultado_final)

        return resultado_final

    ## Manejo de errores globales (idéntico al original)
    except openai.AuthenticationError:
        return NomiFlash.ErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    except openai.APIConnectionError:
        return NomiFlash.ErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    except Exception as e:
        print(f"Error global inesperado en /validar_nominas: {e}")
        return NomiFlash.ErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")


# --- Endpoint 3: Solo para Documentos Auxiliares ---
@router.post(
    "/validar_documentos_auxiliares",
    response_model=Union[NomiFlash.ResultadoConsolidado, NomiFlash.ErrorRespuesta],
    summary="Extrae y valida datos del estado de cuenta y comprobante de domicilio."
)
async def validar_documentos_auxiliares(
    estado_de_cuenta: Optional[UploadFile] = File(None),
    comprobante_de_domicilio: Optional[UploadFile] = File(None)
):
    """
    Sube el estado de cuenta y/o el comprobante de domicilio (PDF).
    El sistema procesa ambos en paralelo, extrae los datos y aplica
    reglas de negocio específicas (ej. vigencia del comprobante).
    """
    try:
        tasks = []

        # 1. Creamos las tareas solo para los documentos auxiliares
        if estado_de_cuenta:
            tasks.append(procesar_estado_cuenta(estado_de_cuenta))

        if comprobante_de_domicilio:
            tasks.append(procesar_comprobante(comprobante_de_domicilio))

        if not tasks:
            # Si no se envió ningún archivo, devuelve un resultado vacío
            return NomiFlash.ResultadoConsolidado()

        # 2. Ejecutamos las tareas en paralelo
        resultados_parciales = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Consolidamos los resultados
        resultado_final = NomiFlash.ResultadoConsolidado()

        for res in resultados_parciales:
            if isinstance(res, Exception):
                error_msg = f"Una de las tareas de procesamiento de doctos falló: {str(res)}"
                print(error_msg)
                continue

            # Asignamos el resultado a su campo correspondiente
            if isinstance(res, NomiFlash.RespuestaEstado):
                resultado_final.Estado = res
            elif isinstance(res, NomiFlash.RespuestaComprobante):
                resultado_final.Comprobante = res

        # 4. APLICAMOS LAS REGLAS DE NEGOCIO
        # La función 'aplicar_reglas_de_negocio' solo aplicará la regla 
        # 'es_menor_a_3_meses' ya que solo tiene datos del comprobante.
        # La regla de RFC no se aplicará al no tener la nómina.
        resultado_final = aplicar_reglas_de_negocio(resultado_final)

        return resultado_final

    ## Manejo de errores globales (idéntico al original)
    except openai.AuthenticationError:
        return NomiFlash.ErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    except openai.APIConnectionError:
        return NomiFlash.ErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    except Exception as e:
        print(f"Error global inesperado en /validar_documentos_auxiliares: {e}")
        return NomiFlash.ErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")