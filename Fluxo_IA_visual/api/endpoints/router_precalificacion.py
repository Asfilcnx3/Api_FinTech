# api/routers/precalificacion.py (solo llamada a servicios, siendo todo muy limpio)
from fastapi import APIRouter, Depends, HTTPException
from ...services.prequalification_service import PrequalificationService
from ...models.responses_precalificacion import PrequalificationResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/precalificacion/{rfc}", response_model=PrequalificationResponse.PrequalificationFinalResponse)
async def precalificar_cliente(
    rfc: str,
    # Inyección de dependencias: FastAPI se encarga de crear el servicio
    service: PrequalificationService = Depends() 
):
    """
    El endpoint completo es una fachada. Solo delega al servicio de dominio.
    """
    try:
        # Una sola línea que hace todo el trabajo pesado
        resultado = await service.analyze_taxpayer(rfc)
        return resultado
    except Exception as e:
        # Aquí solo manejamos errores HTTP
        logger.error(f"Error procesando RFC {rfc}: {e}")
        raise HTTPException(status_code=500, detail="Error interno procesando la precalificación.")