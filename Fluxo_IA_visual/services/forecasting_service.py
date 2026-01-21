import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from ..models.responses_forecasting import Forecast
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class ForecastingService:
    """
    Servicio de cálculo puro. 
    Responsabilidad: Recibir series de tiempo históricas y proyectar valores futuros.
    """

    def generate_forecast(
        self, 
        historical_map: Dict[str, float], 
        horizon: int = 6
    ) -> Forecast.SalesForecastResponse:
        """
        Genera un pronóstico de ventas basado en un mapa {fecha: monto}.
        Maneja automáticamente la escasez de datos.
        """
        # 1. Validación de datos mínimos
        # Necesitamos al menos 3 puntos para trazar una línea decente
        if not historical_map or len(historical_map) < 3:
            return Forecast.SalesForecastResponse(
                method_used="Insufficient Data",
                horizon_months=horizon,
                forecast_data=[],
                insufficient_data=True
            )

        # 2. Preparación del DataFrame (Pandas)
        try:
            # Convertimos dict a DataFrame y ordenamos
            df = pd.DataFrame(list(historical_map.items()), columns=['ds', 'y'])
            df['ds'] = pd.to_datetime(df['ds'])
            df = df.set_index('ds').sort_index()
            
            # Normalización de Frecuencia:
            # Rellenamos meses faltantes con 0.0 (Syntage a veces salta meses si no hubo ventas)
            # Usamos 'MS' (Month Start) para estandarizar al día 1 del mes
            df = df.asfreq('MS', fill_value=0.0)
            
            values = df['y']
            n_obs = len(values)

        except Exception as e:
            logger.error(f"Error preparando datos para forecast: {e}")
            return Forecast.SalesForecastResponse(
                method_used="Error Processing Data",
                horizon_months=horizon,
                forecast_data=[],
                insufficient_data=True
            )

        # 3. Selección de Estrategia (La lógica "Eficiente")
        forecast_vals = []
        method = ""
        
        try:
            if n_obs < 6:
                # ESTRATEGIA A: Promedio Móvil Simple (Pocos datos)
                # Si tenemos muy poco, mejor proyectar el promedio reciente que inventar tendencias.
                method = "Simple Moving Average (Low Data)"
                mean_val = values.mean()
                forecast_vals = [mean_val] * horizon

            elif n_obs < 24:
                # ESTRATEGIA B: Holt's Linear (Tendencia)
                # Detecta si las ventas van subiendo o bajando, pero sin estacionalidad compleja.
                method = "Holt's Linear Trend"
                # trend='add' es robusto a ceros. damped_trend=True evita proyecciones infinitas locas.
                model = ExponentialSmoothing(
                    values, 
                    trend='add', 
                    damped_trend=True, 
                    seasonal=None
                ).fit()
                forecast_vals = model.forecast(horizon).tolist()

            else:
                # ESTRATEGIA C: Holt-Winters (Tendencia + Estacionalidad)
                # Solo si tenemos 2 años completos (24 meses) para detectar ciclos anuales.
                method = "Holt-Winters Seasonal"
                model = ExponentialSmoothing(
                    values, 
                    trend='add', 
                    seasonal='add', 
                    seasonal_periods=12
                ).fit()
                forecast_vals = model.forecast(horizon).tolist()

        except Exception as e:
            # Fallback de seguridad si statsmodels falla (ej: problemas de convergencia)
            logger.warning(f"Fallo en modelo {method}, usando fallback simple. Error: {e}")
            method = "Fallback Mean"
            forecast_vals = [values.mean()] * horizon

        # 4. Cálculo de Tasa de Crecimiento (Contexto extra)
        # Comparar promedio últimos 3 meses vs promedio primeros 3 meses
        growth_rate = 0.0
        if n_obs >= 6:
            recent_avg = values.iloc[-3:].mean()
            start_avg = values.iloc[:3].mean()
            if start_avg > 0:
                growth_rate = (recent_avg - start_avg) / start_avg

        # 5. Construcción de Respuesta
        # Generar fechas futuras
        last_date = df.index[-1]
        future_dates = pd.date_range(start=last_date, periods=horizon + 1, freq='MS')[1:]

        points = []
        for date, val in zip(future_dates, forecast_vals):
            points.append(Forecast.ForecastPoint(
                date=date.strftime("%Y-%m-%d"),
                predicted_revenue=round(max(0.0, float(val)), 2) #, # Evitar ventas negativas
                # lower_bound_75=0.0, # Implementar intervalos requiere más CPU, lo dejamos simple por ahora
                # upper_bound_75=0.0
            ))

        return Forecast.SalesForecastResponse(
            method_used=method,
            horizon_months=horizon,
            forecast_data=points,
            historical_growth_rate=round(growth_rate, 4)
        )