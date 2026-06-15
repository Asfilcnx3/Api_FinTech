# models/responses_analisisTPV.py

from .responses_general import ErrorRespuestaBase # Por si en el futuro se rompe, quitamos esto
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple, Union

# ----- Clases para respuestas de Análisis TPV (Fluxo) -----
class AnalisisTPV:
    """Namespace para todos los modelos relacionados con el analisis de cuenta TPV."""
    class ErrorRespuesta(BaseModel):
        """Error específico para el procesamiento de TPV."""
        nombre_documento: str = Field(default="Desconocido")
        estatus_documento: str = Field(default="fallido")
        detalle_error: str = Field(alias="error")

        class Config:
            populate_by_name = True # Permite que Pydantic acepte tanto 'error' como 'detalle_error' al construirlo

    class Transaccion(BaseModel):
        """Representa una única transacción encontrada dentro del documento."""
        fecha: str = Field(description="Fecha de la transacción extraída del documento.", examples=["15-JUN-26"])
        periodo: str = Field(description="Periodo contable inferido.", examples=["JUNIO 2026"])
        descripcion: str = Field(description="Descripción cruda o unificada del movimiento.", examples=["TRASPASO SPEI A TERCEROS"])
        monto: str = Field(description="Monto en formato string, sin formato de moneda.", examples=["1500.50"])
        tipo: str = Field(description="Clasificación binaria del movimiento.", examples=["abono", "cargo"])
        categoria: str = Field(description="Etiqueta asignada por el motor de clasificación.", examples=["EFECTIVO", "TPV", "GENERAL"])
        es_sospechosa: bool = Field(default=False, description="Bandera de alerta para prevención de fraudes o discrepancias.")
        razon_clasificacion: str = Field(default="", description="Justificación técnica de por qué se asignó la categoría.")
    
    class ResultadoTPV(BaseModel):
        """Representa todas las transacciones TPV encontadas dentro del documento."""
        transacciones: List["AnalisisTPV.Transaccion"] = Field(default_factory=list)
        error_transacciones: Optional[str] = None

    class ResultadoAnalisisIA(BaseModel):
        """Clase de respuesta para un análisis de carátula exitoso."""
        nombre_archivo_virtual: Optional[str] = Field(default=None, description="Nombre asignado en memoria para trazabilidad.", examples=["Estado_Cuenta_Marzo.pdf"])

        # Campos de la carátula
        banco: str = Field(description="Institución bancaria detectada por el motor o la IA.", examples=["BANORTE", "BBVA"])
        tipo_moneda: Optional[str] = Field(default=None, description="Moneda detectada en el documento.", examples=["MXN", "USD"])
        
        rfc: Optional[str] = Field(default=None, description="Registro Federal de Contribuyentes extraído.", examples=["GODE561231GR8"])
        nombre_cliente: Optional[str] = Field(default=None, description="Razón social o nombre del titular.", examples=["COMERCIALIZADORA GODE SA DE CV"])
        clabe_interbancaria: Optional[str] = Field(default=None, description="CLABE de 18 dígitos detectada.", examples=["072320012345678901"])
        periodo_inicio: Optional[str] = Field(default=None, description="Fecha de inicio del ciclo del estado de cuenta.", examples=["01/03/2026"])
        periodo_fin: Optional[str] = Field(default=None, description="Fecha de corte del estado de cuenta.", examples=["31/03/2026"])
        
        comisiones: Optional[float] = Field(default=None, description="Comisiones totales declaradas explícitamente en la carátula.", examples=[1250.50])
        depositos: Optional[float] = Field(default=None, description="Total de depósitos declarados en la carátula.", examples=[350000.00])
        cargos: Optional[float] = Field(default=None, description="Total de retiros o cargos declarados en la carátula.", examples=[345000.00])
        saldo_promedio: Optional[float] = Field(default=None, description="Saldo promedio mensual declarado.", examples=[15000.00])

        # --- CAMPOS ESPECÍFICOS KAPITAL (Sumandos) ---
        kapital_dep_efectivo: Optional[float] = Field(default=0.0, description="Suma de depósitos en efectivo para KAPITAL")
        kapital_dep_cheques: Optional[float] = Field(default=0.0, description="Suma de depósitos en cheques para KAPITAL")
        kapital_transf_recibidas: Optional[float] = Field(default=0.0, description="Suma de transferencias recibidas para KAPITAL")
        kapital_otros_abonos: Optional[float] = Field(default=0.0, description="Suma de otros abonos para KAPITAL")
        kapital_intereses_ganados: Optional[float] = Field(default=0.0, description="Suma de intereses ganados para KAPITAL")
        
        kapital_ret_efectivo: Optional[float] = Field(default=0.0, description="Suma de retiros en efectivo para KAPITAL")
        kapital_cheques_cobrados: Optional[float] = Field(default=0.0, description="Suma de cheques cobrados para KAPITAL")
        kapital_transf_enviadas: Optional[float] = Field(default=0.0, description="Suma de transferencias enviadas para KAPITAL")
        kapital_otros_cargos: Optional[float] = Field(default=0.0, description="Suma de otros cargos para KAPITAL")
        kapital_ret_isr: Optional[float] = Field(default=0.0, description="Suma de retenciones de ISR para KAPITAL")
        kapital_int_prestamos: Optional[float] = Field(default=0.0, description="Suma de intereses de préstamos para KAPITAL")
        kapital_amort_prestamos: Optional[float] = Field(default=0.0, description="Suma de amortizaciones de préstamos para KAPITAL")
        kapital_movimientos_mes_abonos: Optional[float] = Field(default=0.0, description="Abonos de inversión (+) Movimientos del Mes")
        kapital_movimientos_mes_cargos: Optional[float] = Field(default=0.0, description="Cargos de inversión (-) Movimientos del Mes")
        # ---------------------------------------------

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
        """Representa la respuesta consolidada para un documento individual: Carátula + Detalle de Transacciones."""

        # --- CAMPOS DE ESTATUS ---
        nombre_documento: Optional[str] = Field(None, description="Nombre original del archivo procesado.", examples=["lote_01_banco.pdf"])
        estatus_documento: str = Field(
            "exitoso", 
            description="Estado final del procesamiento. Puede ser 'exitoso' o 'fallido'. Un estado fallido implica que se generó un ErrorRespuesta en los detalles.",
            examples=["exitoso"]
        )
        
        AnalisisIA: Optional["AnalisisTPV.ResultadoAnalisisIA"] = Field(None, description="Resultados extraídos de la carátula y métricas globales calculadas.")
        DetalleTransacciones: Optional[Union["AnalisisTPV.ResultadoTPV", "AnalisisTPV.ErrorRespuesta"]] = Field(None, description="Lista de movimientos extraídos o el detalle del error si falló.")

        # --- MÉTRICAS ---
        metadata_tecnica: List[Dict[str, Any]] = Field(default_factory=list, description="Telemetría de extracción por página (tiempo, score, método OCR).")
        
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
