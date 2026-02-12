from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class RespuestasMotorEstados(BaseModel):
    """Namespace para modelos relacionados con el Motor de Estados de Cuenta."""
    
    class ErrorRespuesta(BaseModel):
        """Modelo para representar errores específicos del Motor de Estados de Cuenta."""
        codigo_error: str
        mensaje: str

    # --- ENUMS PARA ESTANDARIZACIÓN ---
    class TipoTransaccion(str, Enum):
        CARGO = "cargo"
        ABONO = "abono"
        SALDO = "saldo"
        INDEFINIDO = "indefinido"

    class MetodoExtraccion(str, Enum):
        """
        Define la heurística utilizada para extraer el dato.
        Esto nos permite saber 'qué tan confiable' es el dato.
        """
        EXACTO_TEXTO = "OK_TEXT_MATCH"         # Match perfecto por monto en texto (Alta Confianza)
        EXACTO_GEO_COLUMNA = "OK_SPATIAL_CLASS" # Match por geometría en columna detectada (Alta Confianza)
        INFERENCIA_GEO = "OK_LEFTMOST_GUESS"   # Match por posición relativa izquierda/derecha (Media Confianza)
        FORZADO = "FORCED_MATCH"               # Match forzado por lógica de descarte (Baja Confianza)
        MANUAL = "MANUAL_OVERRIDE"             # Corrección manual (si aplica en futuro)

    # --- MODELOS DE NIVEL ATÓMICO (TRANSACCIÓN) ---
    class TransaccionDetectada(BaseModel):
        """Representa una única fila bancaria extraída y validada."""

        # Datos del Negocio
        fecha: str = Field(..., description="Fecha en formato normalizado (DD/MM/AAAA o DD/MM)", min_length=3)
        descripcion: str = Field(..., description="Texto completo de la descripción de la operación")
        monto: float = Field(..., description="Monto de la operación")
        tipo: "RespuestasMotorEstados.TipoTransaccion"
        
        # Metadatos Técnicos (Observabilidad)
        id_interno: str = Field(..., description="ID único del bloque (ej: P1_IDX5)")
        score_confianza: float = Field(..., ge=0.0, le=1.0, description="Puntaje de calidad de 0.0 a 1.0")
        metodo_match: "RespuestasMotorEstados.MetodoExtraccion" = Field(..., description="Estrategia usada para encontrar el monto")
        
        # Coordenadas (Opcional, útil para debug visual o UI futura)
        coords_box: Optional[List[float]] = Field(None, description="[x0, y0, x1, y1] del bloque de texto")

        errores: List["RespuestasMotorEstados.ErrorRespuesta"] = Field(default_factory=list, description="Lista de errores o advertencias relacionadas con esta transacción (ej: ['Fecha inconsistente', 'Monto sospechoso'])")

    # --- MODELOS DE NIVEL PÁGINA ---
    class MetricasPagina(BaseModel):
        """Desglose de rendimiento por página individual."""
        numero_pagina: int
        tiempo_procesamiento_ms: float
        cantidad_bloques_detectados: int
        cantidad_transacciones_finales: int
        calidad_promedio_pagina: float = Field(..., ge=0.0, le=1.0)
        alertas: List[str] = Field(default_factory=list, description="Lista de advertencias (ej: 'Ghosting detectado', 'Imagen borrosa')")

    class ResultadoPagina(BaseModel):
        """Contenedor de resultados de una página específica."""
        pagina: int
        metricas: "RespuestasMotorEstados.MetricasPagina"
        transacciones: List["RespuestasMotorEstados.TransaccionDetectada"]

    # --- MODELO DE NIVEL DOCUMENTO (GLOBAL) ---
    class ResumenCalidad(BaseModel):
        """KPIs globales de la extracción."""
        hit_rate: float = Field(..., description="Porcentaje de transacciones de alta confianza (0-100%)")
        score_global_promedio: float = Field(..., description="Promedio ponderado de confianza de todo el documento")
        total_transacciones: int
        desglose_matches: Dict[str, int] = Field(..., description="Conteo por tipo (ej: {'OK_TEXT_MATCH': 50, ...})")
        tiempo_total_segundos: float

    class ReporteMotorDeEstados(BaseModel):
        """
        OUTPUT FINAL DEL SISTEMA.
        Este es el objeto que devolverá la clase BankStatementEngine.
        """
        # Identificación
        filename: str
        fecha_proceso: datetime = Field(default_factory=datetime.now)
        version_motor: str = "3.0.0-Ghostbuster"
        
        # Resultados
        resumen: "RespuestasMotorEstados.ResumenCalidad"
        paginas: List["RespuestasMotorEstados.ResultadoPagina"]
        
        # Lista plana de todas las transacciones (para facilidad de consumo aguas abajo)
        transacciones_consolidadas: List["RespuestasMotorEstados.TransaccionDetectada"]