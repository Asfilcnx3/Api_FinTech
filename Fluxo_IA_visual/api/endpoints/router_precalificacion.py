# api/routers/precalificacion.py (solo llamada a servicios, siendo todo muy limpio)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from ...services.prequalification_service import PrequalificationService
from ...models.responses_precalificacion import PrequalificationResponse
from ...services.syntage_storage_service import StorageService
from ...utils.xlsx_syntage_generator import generar_excel_syntage
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
storage = StorageService()

@router.get("/precalificacion/{rfc}", response_model=PrequalificationResponse.PrequalificationFinalResponse)
async def precalificar_cliente(
    request: Request, # Para construir la URL base
    rfc: str,
    service: PrequalificationService = Depends()
):
    """
    El endpoint completo es una fachada. Solo delega al servicio de dominio.
    """
    rfc = rfc.strip().upper()
    try:
        # 1. Obtener resultado (Tu lógica existente)
        resultado = await service.analyze_taxpayer(rfc)
        
        # 2. Guardar para descarga (NUEVO)
        storage = StorageService()
        # Agregamos parámetros para que vuelque absolutamente todo
        data_dict = resultado.model_dump(exclude_unset=False, exclude_none=False)
        
        job_id = storage.save_json_result(data_dict)
        
        # 3. Inyectar ID y URL en la respuesta
        resultado.job_id = job_id
        # Construye la URL completa: https://api.tu-dominio.com/api/v1/download/report/{uuid}
        base_url = str(request.base_url).rstrip("/")
        resultado.download_url = f"{base_url}/api/v1/download/report/{job_id}"
        
        return resultado
    
    except Exception as e:
        # Aquí solo manejamos errores HTTP
        logger.error(f"Error procesando RFC {rfc}: {e}")
        raise HTTPException(status_code=500, detail="Error interno procesando la precalificación.")
    

@router.get("/download/report/{job_id}")
async def download_syntage_report(job_id: str):
    # 1. Recuperar datos
    data = storage.get_json_result(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="El reporte ha expirado o no existe.")
    
    # 2. Generar Excel (Bytes)
    excel_bytes = generar_excel_syntage(data)
    
    # 3. Retornar archivo
    filename = f"Reporte_Financiero_{data.get('rfc', 'Syntage')}.xlsx"
    
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )