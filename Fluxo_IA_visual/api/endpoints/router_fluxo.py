# routers/router_fluxo.py

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from typing import List
import uuid
import logging

# Servicios
from ...services.file_manager import FileManagerService
from ...services.processing_service import ProcessingService
from ...services.storage_service import obtener_ruta_archivo, obtener_datos_json
from ...models.responses_general import RespuestaProcesamientoIniciado

router = APIRouter()
logger = logging.getLogger(__name__)

# Inyección de dependencias (Manual por ahora)
file_manager = FileManagerService()
processing_service = ProcessingService(file_manager)

@router.post(
    "/fluxo/procesar_pdf/", 
    response_model=RespuestaProcesamientoIniciado,
    summary="Extrae datos estructurados de transacciones TPV."
)
async def procesar_pdf_api(
    background_tasks: BackgroundTasks,
    archivos: List[UploadFile] = File(..., description="Archivos PDF o ZIP")
):
    """
    Endpoint asíncrono. Sube archivos -> Valida -> Lanza proceso en Background -> Retorna ID.
    """
    job_id = str(uuid.uuid4())
    lista_archivos_trabajo = []

    # 1. Cargar y validar archivos (Streaming a Disco)
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

    # 2. Delegar lógica de negocio al servicio (Background)
    background_tasks.add_task(
        processing_service.ejecutar_pipeline_background,
        job_id,
        lista_archivos_trabajo
    )

    return RespuestaProcesamientoIniciado(
        mensaje="Procesamiento iniciado. Descarga los resultados usando el job_id.",
        job_id=job_id,
        estatus="procesando"
    )

# El endpoint de descarga se mantiene igual, ya que solo lee del storage service
@router.get("/fluxo/descargar-resultado/{job_id}")
async def descargar_resultado(job_id: str, formato: str = Query("excel", enum=["excel", "json"])):
    # ... (Tu código existente para descarga está perfecto) ...
    if formato == "json":
        datos = obtener_datos_json(job_id)
        if datos: return datos
        raise HTTPException(status_code=404, detail="No encontrado o procesando.")
    else:
        ruta = obtener_ruta_archivo(job_id)
        if ruta:
            return FileResponse(
                path=ruta, 
                filename=f"Reporte_{job_id}.xlsx",
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        raise HTTPException(status_code=404, detail="Archivo no listo.")