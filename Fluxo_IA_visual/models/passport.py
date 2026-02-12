# models/passport.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class DetalleFase(BaseModel):
    fase_actual: int      # 1 a 5
    nombre_fase: str      # Ej: "Extracción Digital"
    descripcion: str      # Ej: "Analizando página 24 de 50..."
    
class MetricasTecnicas(BaseModel):
    paginas_ocr: int = 0
    paginas_digitales: int = 0
    transacciones_detectadas: int = 0
    tiempo_transcurrido_seg: float = 0.0
    tiempo_estimado_total_seg: float = 0.0 # fórmula dinámica

class PassportData(BaseModel):
    job_id: str
    estado: str = "EN_COLA" # EN_COLA, PROCESANDO, TERMINADO, ERROR
    progreso_porcentaje: float = 0.0
    
    # Información para el Usuario
    detalle: DetalleFase
    metricas: MetricasTecnicas
    
    # Timestamps
    inicio: str
    ultima_actualizacion: str
    eta_estimado: str # Hora estimada de finalización (HH:MM:SS)
    
    logs_recientes: List[str] = [] # Últimos 5 eventos para el usuario "geek"