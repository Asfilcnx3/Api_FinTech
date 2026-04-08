# routers/router_fluxo.py

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, Depends
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional
import uuid
import logging

# Servicios
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
    file_manager: FileManagerService = Depends(get_file_manager)
) -> ProcessingService:
    return ProcessingService(file_manager)

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
    background_tasks: BackgroundTasks,
    archivos: List[UploadFile] = File(..., description="Archivos PDF o ZIP"),
    webhook_url: Optional[str] = Form(None, description="URL para notificar al terminar"),
    # --- INYECCIÓN DE DEPENDENCIAS AQUÍ ---
    file_manager: FileManagerService = Depends(get_file_manager),
    processing_service: ProcessingService = Depends(get_processing_service),
    orquestador: OrquestadorWebhooks = Depends(get_orquestador_general)
):
    job_id = str(uuid.uuid4())
    lista_archivos_trabajo = []

    try:
        for archivo in archivos:
            resultado = file_manager.procesar_entrada(archivo)
            lista_archivos_trabajo.extend(resultado)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error en carga de archivos: {e}")
        raise HTTPException(status_code=500, detail="Error procesando la subida de archivos.")

    if not lista_archivos_trabajo:
        raise HTTPException(status_code=400, detail="No se encontraron archivos PDF válidos.")

    # DELEGAMOS AL ORQUESTADOR GENERAL
    background_tasks.add_task(
        orquestador.ejecutar_y_notificar,
        processing_service.ejecutar_pipeline_background, # 1. La función a ejecutar
        job_id,                                          # 2. El Job ID
        webhook_url,                                     # 3. El webhook
        lista_archivos_trabajo                           # 4. Los *args que necesita tu pipeline
    )

    return RespuestaProcesamientoIniciado(
        mensaje="Procesamiento iniciado. Descarga los resultados usando el job_id o espera el webhook.",
        job_id=job_id,
        estatus="procesando"
    )

@router.get("/fluxo/descargar-resultado/{job_id}")
async def descargar_resultado(
    job_id: str, 
    formato: str = Query("excel", enum=["excel", "json"]),
    # --- INYECCIÓN DE DEPENDENCIAS AQUÍ ---
    storage: StorageService = Depends(get_storage),
    passport_service: PassportService = Depends(get_passport_service)
):
    """
    Intenta descargar. Si no está listo, retorna un 202 (Accepted) con el Pasaporte 
    para que el frontend sepa qué mostrar.
    """
    # 1. Intentar buscar el archivo final
    ruta = storage.obtener_ruta_archivo(job_id) if formato == "excel" else storage.obtener_datos_json(job_id)
    
    if ruta:
        # SI EXISTE, lo entregamos (Código 200 normal)
        if formato == "json": return ruta
        return FileResponse(
            path=ruta, 
            filename=f"Reporte_{job_id}.xlsx",
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    # 2. SI NO EXISTE, buscamos el Pasaporte
    pasaporte = passport_service.leer_pasaporte(job_id)
    
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
    raise HTTPException(status_code=404, detail="Job no encontrado.")