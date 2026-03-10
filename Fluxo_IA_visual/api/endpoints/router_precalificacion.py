# Fluxo_IA_visual/routers/precalificacion.py
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import Response
import logging

from ...services.storage_service import StorageService
from ...services.prequalification.orchestator_prequalification import PrequalificationOrchestrator
from ...services.report_generator.excel_orchestator import ExcelReportBuilder

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
router = APIRouter()
storage = StorageService()

# --- TAREA EN SEGUNDO PLANO ---
async def procesar_precalificacion_bg(rfc: str, job_id: str, orchestrator: PrequalificationOrchestrator):
    """Esta función corre sin bloquear al cliente."""
    try:
        resultado = await orchestrator.analyze_taxpayer(rfc)
        # Volcar datos a dict
        data_dict = resultado.model_dump(exclude_unset=False, exclude_none=False)
        # Añadir banderas de éxito
        data_dict["status"] = "completed"
        data_dict["job_id"] = job_id
        
        storage.update_job(job_id, data_dict)
        logger.info(f"[{rfc}] Job {job_id} completado con éxito.")
    except Exception as e:
        logger.error(f"[{rfc}] Error en Job {job_id}: {e}", exc_info=True)
        storage.update_job(job_id, {"status": "error", "detail": str(e), "rfc": rfc})

# --- ENDPOINTS ---

@router.get("/precalificacion/{rfc}")
async def iniciar_precalificacion(
    request: Request, 
    rfc: str,
    background_tasks: BackgroundTasks, # Inyección de dependencia de FastAPI
    orchestrator: PrequalificationOrchestrator = Depends()
):
    """Retorna un Job ID inmediato e inicia el proceso en el backend."""
    rfc = rfc.strip().upper()
    job_id = storage.create_pending_job(rfc)
    
    # Enviar al background
    background_tasks.add_task(procesar_precalificacion_bg, rfc, job_id, orchestrator)
    
    base_url = str(request.base_url).rstrip("/")
    return {
        "message": "Procesamiento iniciado en segundo plano.",
        "job_id": job_id,
        "status_url": f"{base_url}/api/v1/precalificacion/status/{job_id}",
        "download_url": f"{base_url}/api/v1/precalificacion/download/report/{job_id}"
    }

@router.get("/download/report/{job_id}")
async def download_syntage_report(job_id: str):
    data = storage.get_json_result(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="El reporte no existe o ha expirado.")
    
    # Validaciones de seguridad
    if data.get("status") == "processing":
        raise HTTPException(status_code=400, detail="El reporte aún se está procesando. Intente más tarde.")
    if data.get("status") == "error":
        raise HTTPException(status_code=500, detail="El procesamiento falló, no se puede generar el Excel.")

    # Generar Excel al vuelo solo cuando está completado
    builder = ExcelReportBuilder(data)
    excel_bytes = builder.build()
    
    filename = f"Reporte_Financiero_{data.get('rfc', 'Syntage')}.xlsx"
    
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )