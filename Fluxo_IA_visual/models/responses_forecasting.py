from pydantic import BaseModel
from typing import List, Optional

class Forecast(BaseModel):
    class ForecastPoint(BaseModel):
        date: str  # YYYY-MM-DD
        value: float
    
    class Scenario(BaseModel):
        """
        Representa un escenario de proyección con incertidumbre.
        """
        realistic: List["Forecast.ForecastPoint"]
        optimistic: List["Forecast.ForecastPoint"]  # Realistic + Incertidumbre
        pessimistic: List["Forecast.ForecastPoint"] # Realistic - Incertidumbre

    class ModelResult(BaseModel):
        """
        Resultado de un algoritmo específico (ej. Linear Regression)
        """
        scenarios: "Forecast.Scenario"
        method_name: str
        historical_growth_rate: Optional[float] = None

        # COMPARISON: Crecimiento total pronosticado vs total año anterior
        comparison_realistic: Optional[float] = None 
        comparison_optimistic: Optional[float] = None
        comparison_pessimistic: Optional[float] = None
        
        # TREND: Pendiente interna de la proyección (Mes 12 vs Mes 1)
        trend_realistic: Optional[float] = None
        trend_optimistic: Optional[float] = None
        trend_pessimistic: Optional[float] = None

    class MetricForecast(BaseModel):
        """
        Contiene los 3 modelos posibles para una métrica.
        """
        linear: Optional["Forecast.ModelResult"] = None      # Regresión Lineal Simple
        exponential: Optional["Forecast.ModelResult"] = None # Suavizado (Holt's)
        seasonal: Optional["Forecast.ModelResult"] = None    # Estacional (Holt-Winters)

    class FullForecastResponse(BaseModel):
        horizon_months: int
        revenue: "Forecast.MetricForecast"
        expenditures: "Forecast.MetricForecast"
        inflows: "Forecast.MetricForecast"
        outflows: "Forecast.MetricForecast"
        nfcf: "Forecast.MetricForecast"