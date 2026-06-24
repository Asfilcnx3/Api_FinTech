# api/endpoints/router_fluxo.py

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, Depends
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field
from uuid import UUID
import logging
from fastapi import Request

# Servicios
from ...models.passport import PassportData
from ...services.file_manager import FileManagerService
from ...services.processing_service import ProcessingService
from ...services.storage_service import StorageService
from ...models.responses_general import RespuestaProcesamientoIniciado
from ...services.passport_service import PassportService
from ...services.webhook_service import WebhookService
from ...services.webhook_general_orchestrator import OrquestadorWebhooks

router = APIRouter()
logger = logging.getLogger(__name__)

# =================================================================
# INYECTORES DE DEPENDENCIAS (El estándar de FastAPI)
# =================================================================
def get_storage() -> StorageService: return StorageService()
def get_passport_service() -> PassportService: return PassportService()
def get_file_manager() -> FileManagerService: return FileManagerService()
def get_webhook_service() -> WebhookService: return WebhookService()

# Inyector compuesto: ProcessingService necesita un FileManager
def get_processing_service(
    file_manager: FileManagerService = Depends(get_file_manager),
    passport_service: PassportService = Depends(get_passport_service), 
    storage: StorageService = Depends(get_storage)                     
) -> ProcessingService:
    return ProcessingService(file_manager, passport_service, storage)

# Inyector del Orquestador Universal
def get_orquestador_general(
    storage: StorageService = Depends(get_storage),
    webhook_service: WebhookService = Depends(get_webhook_service)
) -> OrquestadorWebhooks:
    return OrquestadorWebhooks(storage, webhook_service)

# =================================================================
# ENDPOINTS
# =================================================================
@router.post(
    "/fluxo/procesar_pdf/", 
    response_model=RespuestaProcesamientoIniciado,
    summary="Extrae datos estructurados de transacciones TPV."
)
async def procesar_pdf_api(
    request: Request,
    background_tasks: BackgroundTasks,
    archivos: List[UploadFile] = File(..., description="Archivos PDF o ZIP"),
    webhook_url: Optional[str] = Form(None, description="URL para notificar al terminar"),
    job_id_existente: Optional[str] = Form(None, description="Job ID previo para acumular resultados"), # Agregamos este parámetro
    file_manager: FileManagerService = Depends(get_file_manager),
    storage: StorageService = Depends(get_storage), # INYECTAMOS EL STORAGE AQUÍ
    processing_service: ProcessingService = Depends(get_processing_service),
    orquestador: OrquestadorWebhooks = Depends(get_orquestador_general)
):
    # 1. Generar o reutilizar el Job ID (Con sanitización)
    job_id_limpio = job_id_existente.strip() if job_id_existente else None
    
    # Protegemos contra strings vacíos o la palabra "string" que inyecta Swagger UI
    if not job_id_limpio or job_id_limpio.lower() == "string":
        job_id = str(uuid.uuid4())
    else:
        job_id = job_id_limpio
    
    lista_archivos_trabajo = []

    try:
        for archivo in archivos:
            # Nota: El FileManager ya le inyecta el "hash_documento" a cada archivo 
            # gracias a la modificación que hicimos para el primer servicio.
            resultado = file_manager.procesar_entrada(archivo)
            lista_archivos_trabajo.extend(resultado)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error en carga de archivos: {e}")
        raise HTTPException(status_code=500, detail="Error procesando la subida de archivos.")

    if not lista_archivos_trabajo:
        raise HTTPException(status_code=400, detail="No se encontraron archivos PDF válidos.")

    # 2. Registrar el inicio o actualizar historial sin borrarlo
    datos_previos = storage.obtener_datos_json(job_id)
    if not datos_previos:
        datos_previos = {}
        
    datos_previos["estatus"] = "procesando"
    datos_previos["mensaje"] = "Iniciando Pipeline V2 o recuperando caché..."
    
    storage.update_job(job_id, datos_previos)

    # 3. Rescatamos el pool global
    pool_global = request.app.state.process_pool

    # 4. DELEGAMOS AL ORQUESTADOR GENERAL
    background_tasks.add_task(
        orquestador.ejecutar_y_notificar,
        processing_service.ejecutar_pipeline_background, 
        job_id,                                          
        webhook_url,                                     
        lista_archivos_trabajo,
        pool_global 
    )

    return RespuestaProcesamientoIniciado(
        mensaje="Procesamiento iniciado. Descarga los resultados usando el job_id o espera el webhook.",
        job_id=job_id,
        estatus="procesando"
    )

class RespuestaPasaporte(BaseModel):
    mensaje: str = Field(description="Mensaje de estado", examples=["Archivo aún procesando"])
    pasaporte: PassportData = Field(description="Objeto con la telemetría y progreso en tiempo real")

@router.get(
    "/fluxo/descargar-resultado/{job_id}",
    summary="Descarga el reporte final o consulta el progreso (Pasaporte)",
    description="Intenta descargar el resultado. Si aún no está listo, devuelve un código 202 con el estado actual del procesamiento.",
    responses={
        200: {
            "description": "El archivo está listo. Retorna un binario Excel o un JSON dependiendo del formato solicitado.",
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "example": "Binario del archivo Excel (.xlsx)"
                },
                "application/json": {
                    "example": {"tu_data": "json"}
                }
            }
        },
        202: {
            "description": "El procesamiento sigue en curso. Utiliza el pasaporte para actualizar la barra de progreso en el frontend.",
            "model": RespuestaPasaporte
        },
        404: {
            "description": "El Job ID no existe, expiró o fue eliminado por limpieza automática."
        }
    }
)
async def descargar_resultado(
    job_id: UUID, 
    formato: str = Query("excel", enum=["excel", "json"]),
    storage: StorageService = Depends(get_storage),
    passport_service: PassportService = Depends(get_passport_service)
):
    """
    Intenta descargar. Si no está listo, retorna un 202 (Accepted) con el Pasaporte 
    para que el frontend sepa qué mostrar.
    """
    job_id_str = str(job_id)
    
    # 1. Intentar buscar el archivo final
    ruta = storage.obtener_ruta_archivo(job_id_str) if formato == "excel" else storage.obtener_datos_json(job_id_str)
    
    if ruta:
        # SI EXISTE, lo entregamos (Código 200 normal)
        if formato == "json": return ruta
        return FileResponse(
            path=ruta, 
            filename=f"Reporte_{job_id_str}.xlsx",
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    # 2. SI NO EXISTE, buscamos el Pasaporte
    pasaporte = passport_service.leer_pasaporte(job_id_str)
    
    if pasaporte:
        # Retornamos 202 Accepted (estándar REST para "estoy en ello")
        return JSONResponse(
            status_code=202, 
            content={
                "mensaje": "Archivo aún procesando",
                "pasaporte": pasaporte
            }
        )

    # 3. Si no hay ni archivo ni pasaporte -> 404
    raise HTTPException(status_code=404, detail="Job no encontrado o expirado.")