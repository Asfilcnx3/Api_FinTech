# NOTA: Este archivo define los modelos de datos que se utilizan para estructurar las respuestas que se envían al frontend.
# Aquí se crean modelos ligeros y específicos para la Carátula, que es el primer nivel de extracción que se le muestra al usuario antes de procesar el PDF completo.

from pydantic import BaseModel, Field
from typing import List, Optional

class DatosCaratulaLight(BaseModel):
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