from pydantic import BaseModel
from typing import Any, Dict, Dict, List, Optional
from .responses_forecasting import Forecast


class PrequalificationResponse(BaseModel):

    class CredentialInfo(BaseModel):
        status: str # "active", "inactive", "not_found", "positive", "negative"
        last_check_date: Optional[str] = None # "YYYY-MM-DD" o ISO format
    
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

    class BuroInfo(BaseModel):
        has_report: bool
        status: str # "found", "not_found", "entity_not_found"
        score: Optional[str] = None
        last_check_date: Optional[str] = None # Fecha de la última corrida

        # Detalles del reporte
        credit_lines: List["PrequalificationResponse.BuroCreditLine"] = []
        inquiries: List["PrequalificationResponse.BuroInquiry"] = []
    
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
        median_growth_rate: Optional[float] = None # Crecimiento vs periodo anterior (Opción A)
        linear_slope: float       # Pendiente (Slope) de regresión lineal
        cagr_cmgr: float          # Compound Growth Rate (Annual or Monthly)
    
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

    class ConcentrationMetrics(BaseModel):
        top_5_clients: List["PrequalificationResponse.ConcentrationItem"]
        top_5_suppliers: List["PrequalificationResponse.ConcentrationItem"]

    class FinancialYearInput(BaseModel): # --- INPUT PARA CALCULADORA ---
        """Datos crudos extraídos del árbol para un año específico"""
        year: str
        assets: float = 0.0
        equity: float = 0.0
        revenue: float = 0.0
        taxes: float = 0.0
        
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

        # -- Datos Crudos (Evidencia del cálculo) --
        input_assets: float
        input_equity: float
        input_revenue: float
        input_net_income: float # El valor final resuelto (signo corregido)
        input_taxes: float

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
        financial_ratios_history: List["PrequalificationResponse.FinancialRatioYear"]
        
        # Forecast y descarga
        financial_predictions: Optional[Any] = None
        job_id: Optional[str] = None
        download_url: Optional[str] = None