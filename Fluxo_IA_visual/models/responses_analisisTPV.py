from .responses_general import ErrorRespuestaBase
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Union

# ----- Clases para respuestas de Análisis TPV (Fluxo) -----
class AnalisisTPV:
    """Namespace para todos los modelos relacionados con el analisis de cuenta TPV."""
    class ErrorRespuesta(ErrorRespuestaBase):
        """Error específico para el procesamiento de TPV."""
        pass

    class Transaccion(BaseModel):
        """Representa una única transaccion encontrada dentro del documento [3 partes]."""
        fecha: str
        descripcion: str
        monto: str
        tipo: str
        categoria: str
    
    class ResultadoTPV(BaseModel):
        """Representa todas las transacciones TPV encontadas dentro del documento."""
        transacciones: List["AnalisisTPV.Transaccion"] = Field(default_factory=list)
        error_transacciones: Optional[str] = None

    class ResultadoAnalisisIA(BaseModel):
        """Clase de respuesta para un analisis de carátula exitóso."""
        banco: str
        tipo_moneda: Optional[str] = None
        rfc: Optional[str] = None
        nombre_cliente: Optional[str] = None
        clabe_interbancaria: Optional[str] = None
        periodo_inicio: Optional[str] = None
        periodo_fin: Optional[str] = None
        comisiones: Optional[float] = None
        depositos: Optional[float] = None
        cargos: Optional[float] = None
        saldo_promedio: Optional[float] = None
        depositos_en_efectivo: Optional[float] = None
        traspaso_entre_cuentas: Optional[float] = None
        total_entradas_financiamiento: Optional[float] = None
        entradas_bmrcash: Optional[float] = None
        total_moratorios: Optional[float] = None
        entradas_TPV_bruto: Optional[float] = None
        entradas_TPV_neto: Optional[float] = None

    class ResultadoExtraccion(BaseModel):
        """Representa la respuesta para los documentos individuales -> Caratula + Resultados TPV."""
        AnalisisIA: Optional["AnalisisTPV.ResultadoAnalisisIA"] = None
        DetalleTransacciones: Optional[Union["AnalisisTPV.ResultadoTPV", "AnalisisTPV.ErrorRespuesta"]] = None
        
        # --- CAMPOS INTERNOS (Contexto para Geometría) ---
        # exclude=True hace que estos campos existan en Python pero NO en el JSON final
        file_path_origen: Optional[str] = Field(default=None, exclude=True)
        rango_paginas: Optional[Tuple[int, int]] = Field(default=None, exclude=True)
        es_digital: bool = Field(default=True, exclude=True)

    class ResultadoTotal(BaseModel):
        """Representa una respuesta exitosa de todos los lotes analizados."""
        total_depositos: Optional[float] = None # Representa lógica interna
        es_mayor_a_250: Optional[bool] = None # Representa logica interna
        resultados_generales: List["AnalisisTPV.ResultadoAnalisisIA"] # -> Representa únicamente la caratula del estado de cuenta
        resultados_individuales: List["AnalisisTPV.ResultadoExtraccion"] # - > Representa el analisis completo (caratula + tpv)
