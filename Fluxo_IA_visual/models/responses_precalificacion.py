from pydantic import BaseModel
from typing import Any, Dict, Dict, List, Optional
from .responses_forecasting import Forecast


class PrequalificationResponse(BaseModel):

    class CredentialInfo(BaseModel):
        status: str # "active", "inactive", "not_found", "positive", "negative"
        last_check_date: Optional[str] = None # "YYYY-MM-DD" o ISO format

    class BuroInfo(BaseModel):
        has_report: bool
        status: str # "found", "not_found", "entity_not_found"
        score: Optional[str] = None
        last_check_date: Optional[str] = None # Fecha de la última corrida
    
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

    class StatsWindows(BaseModel):
        # Define los periodos de tiempo)
        last_3_months: "PrequalificationResponse.CashflowMetrics"
        last_6_months: "PrequalificationResponse.CashflowMetrics"
        last_12_months: "PrequalificationResponse.CashflowMetrics"
        last_16_months: "PrequalificationResponse.CashflowMetrics"
        last_18_months: "PrequalificationResponse.CashflowMetrics"
        last_24_months: "PrequalificationResponse.CashflowMetrics"

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

        # Indicadores de riesgo (Lista de strings)
        risk_indicators: Dict[str, Any]
    
        # Credenciales
        ciec_info: "PrequalificationResponse.CredentialInfo"
        buro_info: "PrequalificationResponse.BuroInfo"
        compliance_opinion: "PrequalificationResponse.CredentialInfo" # Opinión de cumplimiento (32-D)
        
        # Cashflow histórico (12 meses cerrados)
        stats_last_months: "PrequalificationResponse.StatsWindows"
        
        # Mes actual (en curso)
        cashflow_current_month: Optional["PrequalificationResponse.CurrentMonthMetrics"]
        concentration_last_12m: "PrequalificationResponse.ConcentrationMetrics"
        
        # Razones financieras por año (Lista de objetos por año disponible)
        financial_ratios_history: List["PrequalificationResponse.FinancialRatioYear"]
        sales_forecast: Optional["Forecast.SalesForecastResponse"] = None