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
        growth_realistic: Optional[float] = None
        growth_optimistic: Optional[float] = None
        growth_pessimistic: Optional[float] = None

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