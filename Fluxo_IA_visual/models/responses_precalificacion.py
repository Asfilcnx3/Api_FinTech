from pydantic import BaseModel
from typing import Any, Dict, Dict, List, Optional
from .responses_forecasting import Forecast


class PrequalificationResponse(BaseModel):

    class CredentialInfo(BaseModel):
        status: str # "active", "inactive", "not_found", "positive", "negative"
        last_check_date: Optional[str] = None # "YYYY-MM-DD" o ISO format
        last_extraction_date: Optional[str] = None
    
    class MopBreakdown(BaseModel):
        mop_1: int = 0
        mop_2: int = 0
        mop_3: int = 0
        mop_4: int = 0
        mop_5: int = 0
        mop_6: int = 0
        mop_7: int = 0
        mop_9: int = 0
        mop_0: int = 0
        mop_u: int = 0
        mop_nd: int = 0  # Para el guión "-"
        mop_lc: int = 0
    
    class BuroCreditLine(BaseModel):
        """
        Docstring for BuroCreditLine

        :var para: Description
        :vartype para: Revenue
        """
        institution: str       # nombreOtorgante
        account_type: str      # tipoContrato / tipoCuenta
        credit_limit: float    # limiteCredito / creditoMaximo
        current_balance: float # saldoActual
        past_due_balance: float # saldoVencido
        payment_frequency: str # frecuenciaPagos
        opening_date: Optional[str] # fechaAperturaCuenta
        last_payment_date: Optional[str] # fechaUltimoPago
        payment_history: str   # historicoPagos (ej. "111000")
        update_date: Optional[str] = None # Para el Último Periodo Actualizado
        mop_breakdown: Optional["PrequalificationResponse.MopBreakdown"] = None
        
        # --- CAMPOS CRUDOS ---
        account_number: str = ""
        user_type: str = ""
        closing_date: Optional[str] = None
        term_days: int = 0
        currency: str = "MXN"
        exchange_rate: float = 1.0
        max_delay: int = 0
        initial_balance: float = 0.0
        
        # --- CAMPOS CALCULADOS ---
        weighting_pct: float = 0.0          # Ponderación 1 (%)
        remaining_term_days: int = 0        # Plazo Restante
        weighting_days: float = 0.0         # Ponderación 2 (Plazo Restante * Ponderacion 1)
        final_date: Optional[str] = None    # Fecha Final
        monthly_payment: float = 0.0        # Pago Mensual

    class BuroInquiry(BaseModel):
        """
        Docstring for BuroInquiry
        
        :var para: Description
        :vartype para: Revenue
        """
        institution: str       # nombreOtorgante
        inquiry_date: str      # fechaConsulta
        contract_type: str     # tipoContrato (ej. CC, CL)
        amount: float          # importeContrato
    
    class InquirySummaryRow(BaseModel):
        concept: str
        quantity: int
        equivalent_months: Optional[int] = None
        monthly_average: Optional[float] = None
        growth_vs_previous: Optional[float] = None
    
    class BuroBucket(BaseModel):
        amount: float
        percentage: float

    class BuroSummaryMetrics(BaseModel):
        inquiries_trend_text: str
        inquiries_trend_pct: float
        
        total_open_max_amount: float
        total_current_balance: float
        total_past_due: float
        monthly_payment_1: float
        monthly_payment_2: float
        weighted_term_years: float
        
        bucket_1_29: "PrequalificationResponse.BuroBucket"
        bucket_30_59: "PrequalificationResponse.BuroBucket"
        bucket_60_89: "PrequalificationResponse.BuroBucket"
        bucket_90_119: "PrequalificationResponse.BuroBucket"
        bucket_120_179: "PrequalificationResponse.BuroBucket"
        bucket_180_plus: "PrequalificationResponse.BuroBucket"

    class BuroInfo(BaseModel):
        has_report: bool
        status: str # "found", "not_found", "entity_not_found"
        score: Optional[str] = None
        last_check_date: Optional[str] = None # Fecha de la última corrida

        # Detalles del reporte
        credit_lines: List["PrequalificationResponse.BuroCreditLine"] = []
        inquiries: List["PrequalificationResponse.BuroInquiry"] = []

        # --- RESUMEN MATEMÁTICO ---
        inquiries_summary: List["PrequalificationResponse.InquirySummaryRow"] = []
        summary_metrics: Optional["PrequalificationResponse.BuroSummaryMetrics"] = None
        
        # --- CONTENEDOR PARA VOLCADO TOTAL ---
        raw_buro_data: Dict[str, Any] = {}
    
    class EconomicActivity(BaseModel):
        name: str
        percentage: float
        start_date: Optional[str] = None # "YYYY-MM-DD"
    
    class Stats(BaseModel):
        mean: float
        median: float

    class CashflowMetrics(BaseModel):
        # Stats de los 12 meses COMPLETOS anteriores
        inflows_stats: "PrequalificationResponse.Stats"
        outflows_stats: "PrequalificationResponse.Stats"
        nfcf_stats: "PrequalificationResponse.Stats"
        expenditures_stats: "PrequalificationResponse.Stats"  
        sales_revenue_stats: "PrequalificationResponse.Stats" 

    class AdvancedPeriodMetrics(BaseModel):
        """
        Nuevas métricas solicitadas por auditoría.
        Se calcularán para: Revenue, Expenses, Inflows, Outflows, NFCF
        """
        mean: float               # Promedio
        median: float             # Mediana absoluta pura
        period_growth_rate: Optional[float] = None # Crecimiento total vs periodo anterior
        linear_slope: float       # Pendiente (Slope) de regresión lineal
        cagr_cmgr: float          # Compound Growth Rate
    
    class PeriodGroup(BaseModel):
        """
        Agrupa las 5 verticales financieras para un periodo de tiempo (ej. Last 3 Months)
        """
        revenue: "PrequalificationResponse.AdvancedPeriodMetrics"
        expenditures: "PrequalificationResponse.AdvancedPeriodMetrics"
        inflows: "PrequalificationResponse.AdvancedPeriodMetrics"
        outflows: "PrequalificationResponse.AdvancedPeriodMetrics"
        nfcf: "PrequalificationResponse.AdvancedPeriodMetrics"

    class StatsWindows(BaseModel):
        """
        Contenedor para las métricas financieras en varias ventanas de tiempo.
        """
        last_24_months: Optional["PrequalificationResponse.PeriodGroup"]
        last_12_months: Optional["PrequalificationResponse.PeriodGroup"]
        last_9_months: Optional["PrequalificationResponse.PeriodGroup"]
        last_6_months: Optional["PrequalificationResponse.PeriodGroup"]
        last_3_months: Optional["PrequalificationResponse.PeriodGroup"]

    class CurrentMonthMetrics(BaseModel):
        # Datos crudos del mes incompleto actual
        month: str
        inflows: float
        outflows: float
        nfcf: float
        sales_revenue: float 
        expenditures: float  

    class ConcentrationItem(BaseModel):
        name: str
        rfc: str # Ahora sí obligatorio
        total_amount: float
        percentage: float
        linear_slope: float = 0.0
        trend_text: str = "Sin datos"

    class ConcentrationMetrics(BaseModel):
        top_5_clients: List["PrequalificationResponse.ConcentrationItem"]
        top_5_suppliers: List["PrequalificationResponse.ConcentrationItem"]

    class FinancialYearInput(BaseModel): # --- INPUT PARA CALCULADORA ---
        """Datos crudos extraídos del árbol para un año específico"""
        year: str
        assets: float = 0.0
        liabilities: float = 0.0 # Pasivos
        equity: float = 0.0
        revenue: float = 0.0
        taxes: float = 0.0

        gross_profit: float = 0.0 # Utilidad Bruta
        gross_loss: float = 0.0   # Pérdida Bruta
        
        # Dual fields (Syntage separa Profit de Loss)
        net_profit: float = 0.0
        net_loss: float = 0.0
        
        ebit_profit: float = 0.0
        ebit_loss: float = 0.0
        
        ebt_profit: float = 0.0
        ebt_loss: float = 0.0

    class FinancialRatioYear(BaseModel): # --- OUTPUT DE CALCULADORA ---
        year: str
        roa: float
        roe: float
        net_profit_margin_percent: float # Margen neto de utilidad (%)
        ebit: float
        ebt: float
        nopat: float

        # -- Datos Consolidados --
        input_assets: float
        input_liabilities: float     # Pasivo
        input_equity: float
        input_revenue: float
        input_gross_profit: float    # Bruta consolidada (Profit - Loss)
        input_net_income: float
        input_taxes: float
        
        # --- Datos Crudos  ---
        raw_net_profit: float = 0.0
        raw_net_loss: float = 0.0
        raw_ebit_profit: float = 0.0
        raw_ebit_loss: float = 0.0
        raw_ebt_profit: float = 0.0
        raw_ebt_loss: float = 0.0
    
    class RawDataPoint(BaseModel):
        """Modelo para la nueva hoja de Raw Data"""
        date: str  # YYYY-MM-DD
        revenue: float = 0.0
        expenses: float = 0.0
        inflows_amount: float = 0.0
        outflows_amount: float = 0.0
        nfcf: float = 0.0
        inflows_count: int = 0
        outflows_count: int = 0
    
    class NetworkNode(BaseModel):
        """Modelo para un nodo de red (Cliente o Proveedor)"""
        name: str # Mapearemos 'customer' o 'vendor' aquí
        total_received: float
        total_cancelled_received: float
        percentage_cancelled: float
        received_discounts: float
        received_credit_notes: float
        payment_pending: float # Mapearemos 'emittedPaymentPending' o 'receivedPaymentPending'
        net_received: float
        pue_received: float
        ppd_received: float
        ppd_count: int
        payment_amount: float
        in_installments: float # Mapearemos 'collectedInInstallments' o 'paidInInstallments'
        days_outstanding: float # Mapearemos 'daysSalesOutstanding' o 'daysPayableOutstanding'

    class NetworksData(BaseModel):
        """Contenedor para ambas redes"""
        customers: List["PrequalificationResponse.NetworkNode"] = []
        vendors: List["PrequalificationResponse.NetworkNode"] = []
    
    class ProductServiceItem(BaseModel):
        """Modelo para un producto/servicio vendido o comprado"""
        description: str
        sat_code: str
        total_amount: float
        percentage: float
        transactions: int

    class ProductsData(BaseModel):
        """Contenedor para productos vendidos y comprados"""
        sold: List["PrequalificationResponse.ProductServiceItem"] = []
        bought: List["PrequalificationResponse.ProductServiceItem"] = []

    class PrequalificationFinalResponse(BaseModel):
        rfc: str
        business_name: str
        
        # Nuevos campos
        tax_registration_date: Optional[str] = None
        economic_activities: List["PrequalificationResponse.EconomicActivity"] = []

        risk_indicators: List[Dict[str, Any]] = []
        ciec_info: "PrequalificationResponse.CredentialInfo"
        buro_info: "PrequalificationResponse.BuroInfo"
        compliance_opinion: "PrequalificationResponse.CredentialInfo"
        
        stats_last_months: "PrequalificationResponse.StatsWindows"
        
        # Mes actual (en curso)
        cashflow_current_month: Optional["PrequalificationResponse.CurrentMonthMetrics"] = None
        
        concentration_last_12m: "PrequalificationResponse.ConcentrationMetrics"
        networks_data: "PrequalificationResponse.NetworksData"
        products_data: "PrequalificationResponse.ProductsData"
        financial_ratios_history: List["PrequalificationResponse.FinancialRatioYear"]
        
        # Arbol financiero completo (sin procesar, para auditoría y transparencia)
        financial_statements_tree: Dict[str, Any] = {}

        # Datos crudos para la nueva hoja de Raw Data (12 meses anteriores + mes actual)
        raw_data_history: List["PrequalificationResponse.RawDataPoint"] = []
        
        # Forecast y descarga
        financial_predictions: Optional[Any] = None
        job_id: Optional[str] = None
        download_url: Optional[str] = None