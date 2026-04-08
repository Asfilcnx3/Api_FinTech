# NOTA: Este archivo define los modelos de datos que se utilizan para estructurar las respuestas que se envían al frontend.
# Aquí se crean modelos ligeros y específicos para la Carátula, que es el primer nivel de extracción que se le muestra al usuario antes de procesar el PDF completo.

from pydantic import BaseModel, Field
from typing import List, Optional

class DatosCaratulaLight(BaseModel):
    nombre_documento: Optional[str] = Field(None, description="Nombre original del archivo procesado")
    estatus_documento: Optional[str] = Field("exitoso", description="Estatus del documento")
    banco: Optional[str] = Field(None, description="Nombre del banco en minúsculas (ej. bbva, banorte)")
    clabe: Optional[str] = Field(None, description="CLABE interbancaria de 18 dígitos")
    periodo: Optional[str] = Field(None, description="Periodo del estado de cuenta en formato MM-YYYY")

class RespuestaCaratulasFrontend(BaseModel):
    """Contenedor final para cumplir con la lista de objetos o devolver un error estructurado."""
    resultados: List[DatosCaratulaLight] = []
    error_procesamiento: Optional[str] = None

class RespuestaProcesamientoIniciado(BaseModel):
    mensaje: str
    job_id: str
    estatus: str

class ErrorDocumento(BaseModel):
    nombre_documento: str
    estatus_documento: str = "fallido"
    detalle_error: str

class RespuestaEstadoTrabajo(BaseModel):
    """Modelo para la respuesta del polling (GET) y del payload del Webhook."""
    job_id: str
    estatus: str
    mensaje: Optional[str] = None
    indicador_caratulas_recientes: Optional[bool] = Field(
        None, 
        description="True si existen carátulas de los últimos 3 meses requeridos."
    )
    resultados_exitosos: List[DatosCaratulaLight] = []
    errores: List[ErrorDocumento] = [] 
    detalle_error: Optional[str] = None