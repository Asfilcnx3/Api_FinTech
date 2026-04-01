from .responses_general import ErrorRespuestaBase
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple, Union

# ----- Clases para respuestas de Análisis TPV (Fluxo) -----
class AnalisisTPV:
    """Namespace para todos los modelos relacionados con el analisis de cuenta TPV."""
    class ErrorRespuesta(ErrorRespuestaBase):
        """Error específico para el procesamiento de TPV."""
        pass

    class Transaccion(BaseModel):
        """Representa una única transaccion encontrada dentro del documento [3 partes]."""
        fecha: str
        periodo: str
        descripcion: str
        monto: str
        tipo: str
        categoria: str
        es_sospechosa: bool = False
    
    class ResultadoTPV(BaseModel):
        """Representa todas las transacciones TPV encontadas dentro del documento."""
        transacciones: List["AnalisisTPV.Transaccion"] = Field(default_factory=list)
        error_transacciones: Optional[str] = None

    class ResultadoAnalisisIA(BaseModel):
        """Clase de respuesta para un analisis de carátula exitóso."""
        nombre_archivo_virtual: Optional[str] = None

        # Campos de la carátula
        banco: str
        tipo_moneda: Optional[str] = Field(default=None, description="Ejemplo: MXN, USD, etc.")
        
        rfc: Optional[str] = Field(default=None, description="Ejemplo: GODE561231GR8")
        nombre_cliente: Optional[str] = Field(default=None, description="Nombre del cliente")
        clabe_interbancaria: Optional[str] = Field(default=None, description="CLABE interbancaria")
        periodo_inicio: Optional[str] = Field(default=None, description="Período de inicio")
        periodo_fin: Optional[str] = Field(default=None, description="Período de fin")
        
        comisiones: Optional[float] = Field(default=None, description="Comisiones totales del período que se muestran en la carátula")
        depositos: Optional[float] = Field(default=None, description="Total de depósitos del período que se muestran en la carátula")
        cargos: Optional[float] = Field(default=None, description="Total de cargos del período que se muestran en la carátula")
        saldo_promedio: Optional[float] = Field(default=None, description="Saldo promedio del período que se muestran en la carátula")

        # Métricas de medición
        total_depositos_extraidos: Optional[float] = Field(default=0.0, description="Suma real de los abonos encontrados")
        total_cargos_extraidos: Optional[float] = Field(default=0.0, description="Suma real de los cargos encontrados")

        # Campos específicos de clasificación
        depositos_en_efectivo: Optional[float] = Field(default=0.0, description="Suma de depósitos en efectivo")
        total_entradas_financiamiento: Optional[float] = Field(default=0.0, description="Suma de entradas por financiamiento o créditos")
        entradas_bmrcash: Optional[float] = Field(default=0.0, description="Suma de entradas por BMRCASH")
        total_moratorios: Optional[float] = Field(default=0.0, description="Suma de cargos moratorios")
        entradas_TPV_bruto: Optional[float] = Field(default=0.0, description="Suma de entradas brutas por TPV")
        entradas_TPV_neto: Optional[float] = Field(default=0.0, description="Suma de entradas netas por TPV")
        traspasos_abonos: Optional[float] = Field(default=0.0, description="Suma de traspasos como abonos")
        traspasos_cargos: Optional[float] = None
        pagos_financiamiento: Optional[float] = Field(default=0.0, description="Suma de pagos a financiamientos o créditos")

        # Campos para comisiones de TPV
        comisiones_credito: Optional[float] = Field(default=0.0, description="Comisiones por TPV Crédito")
        comisiones_debito: Optional[float] = Field(default=0.0, description="Comisiones por TPV Débito")
        comisiones_amex: Optional[float] = Field(default=0.0, description="Comisiones por TPV AMEX")
        comisiones_totales: Optional[float] = Field(default=0.0, description="Suma de las 3 anteriores + comisiones genéricas de terminal")

        # Métricas de medición
        confianza_extraccion: Optional[float] = Field(default=None, description="Porcentaje de cuadre entre la carátula y los movimientos extraídos (0.0 a 100.0)")

        # Métrica de Descuadres
        descuadre_depositos: Optional[float] = Field(default=0.0, description="Diferencia absoluta en depósitos")
        descuadre_cargos: Optional[float] = Field(default=0.0, description="Diferencia absoluta en cargos")

        # Métrica de la taza de categorización
        tasa_categorizacion: Optional[float] = Field(default=0.0, description="Porcentaje de transacciones categorizadas exitosamente (distinto a GENERAL)")

        # Métrica de páginas fallidas
        paginas_totales: Optional[int] = Field(default=0, description="Total de páginas procesadas")
        paginas_fallidas: Optional[int] = Field(default=0, description="Páginas que fallaron o no arrojaron transacciones")

    class ResultadoExtraccion(BaseModel):
        """Representa la respuesta para los documentos individuales -> Caratula + Resultados TPV."""
        AnalisisIA: Optional["AnalisisTPV.ResultadoAnalisisIA"] = None
        DetalleTransacciones: Optional[Union["AnalisisTPV.ResultadoTPV", "AnalisisTPV.ErrorRespuesta"]] = None

        # --- MÉTRICAS ---
        # Usamos List[Dict[str, Any]] para máxima flexibilidad
        metadata_tecnica: List[Dict[str, Any]] = Field(default_factory=list)
        
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
