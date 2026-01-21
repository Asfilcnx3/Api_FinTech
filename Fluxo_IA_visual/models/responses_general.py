from typing import Optional
from pydantic import BaseModel

class RespuestaProcesamientoIniciado(BaseModel):
    mensaje: str
    job_id: str
    estatus: str
    
# ---- Modelos base reutilizables ----
class ErrorRespuestaBase(BaseModel):
    """Modelo base para respuestas de error estandarizadas."""
    error: str

class ContribuyenteBaseFisica(BaseModel):
    """Modelo base para la identificación del contribuyente (RFC y CURP)."""
    rfc: Optional[str] = None
    curp: Optional[str] = None

class ContribuyenteBaseMoral(BaseModel):
    """Modelo base para la identificación del contribuyente moral."""
    rfc: Optional[str] = None
    razon_social: Optional[str] = None
    regimen_capital: Optional[str] = None
    nombre_comercial: Optional[str] = None