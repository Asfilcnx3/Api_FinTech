from pydantic import BaseModel
from typing import List, Optional
from .responses_forecasting import Forecast


class PrequalificationResponse(BaseModel):
    
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

        # Credenciales
        ciec_status: str = "unknown" # active, invalid, inactive
        buro_status: str = "unknown"
        buro_score_estimate: Optional[str] = None # Nuevo campo

        # Indicadores de riesgo (Lista de strings)
        risk_indicators: List[str]
        
        # Cashflow histórico (12 meses cerrados)
        cashflow_last_12m: "PrequalificationResponse.CashflowMetrics"
        
        # Mes actual (en curso)
        cashflow_current_month: Optional["PrequalificationResponse.CurrentMonthMetrics"]
        concentration_last_12m: "PrequalificationResponse.ConcentrationMetrics"
        
        # Razones financieras por año (Lista de objetos por año disponible)
        financial_ratios_history: List["PrequalificationResponse.FinancialRatioYear"]
        sales_forecast: Optional["Forecast.SalesForecastResponse"] = None