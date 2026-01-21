from pydantic import BaseModel
from typing import List, Optional

class Forecast(BaseModel):
    class ForecastPoint(BaseModel):
        date: str # YYYY-MM-DD
        predicted_revenue: float
        # lower_bound_75: float = 0.0 # Opcional -- intervalos de confianza
        # upper_bound_75: float = 0.0

    class SalesForecastResponse(BaseModel):
        method_used: str  # Ej: "Holt-Winters", "Simple Moving Average"
        horizon_months: int
        forecast_data: List["Forecast.ForecastPoint"]

        # Flags informativos
        insufficient_data: bool = False
        historical_growth_rate: Optional[float] = None # Tasa de crecimiento promedio detectada