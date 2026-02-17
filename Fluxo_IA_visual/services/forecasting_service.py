import pandas as pd
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from ..models.responses_forecasting import Forecast
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class ForecastingService:
    """
    Servicio de cálculo de series de tiempo financieras v2.0. Siguiendo el siguiente plan:
    
    - Sincronización de Datos: Sigue la regla "El líder manda". Revenue corta a Inflows, Expenditures corta a Outflows.
    
    Arquitectura de 3 Modelos:
        - Linear (Regresión): La línea recta sólida (Mínimos Cuadrados). Muy estable.
        - Exponential (Suavizado): Detecta cambios de tendencia recientes. sin damped agresivo para que no se vaya a cero.
        - Seasonal (Holt-Winters): Solo si hay >24 meses.

    - Cono de Incertidumbre: Para cada modelo, calcularemos el Error Estándar de los datos históricos y proyectaremos 3 líneas: Optimista, Realista (Central), Pesimista.
    Soporta: Sincronización de Series, Multi-Modelos e Incertidumbre.
    """

    def generate_complete_forecast(
        self, 
        revenue_map: Dict[str, float],
        expenditure_map: Dict[str, float],
        inflow_map: Dict[str, float],
        outflow_map: Dict[str, float],
        horizon: int = 12
    ) -> Forecast.FullForecastResponse:
        """
        Orquestador principal.
        Genera 4 proyecciones base y calcula la 5ta (NFCF) derivándola.
        """
        # 1. SINCRONIZACIÓN DE DATOS (Regla: Líder manda)
        # Revenue limpia a Inflows | Expenditures limpia a Outflows
        clean_revenue, clean_inflows = self._sync_series(revenue_map, inflow_map, "Revenue->Inflows")
        clean_expenditures, clean_outflows = self._sync_series(expenditure_map, outflow_map, "Expenditures->Outflows")

        # 2. GENERACIÓN DE PROYECCIONES BASE
        revenue_forecast = self._process_metric(clean_revenue, horizon, "Revenue")
        expenditures_forecast = self._process_metric(clean_expenditures, horizon, "Expenditures")
        inflows_forecast = self._process_metric(clean_inflows, horizon, "Inflows")
        outflows_forecast = self._process_metric(clean_outflows, horizon, "Outflows")

        # 3. CÁLCULO DE NFCF (Derivado para todos los modelos)
        # Se calcula restando Inflows - Outflows en cada escenario de cada modelo
        nfcf_forecast = self._calculate_derived_nfcf(inflows_forecast, outflows_forecast)

        return Forecast.FullForecastResponse(
            horizon_months=horizon,
            revenue=revenue_forecast,
            expenditures=expenditures_forecast,
            inflows=inflows_forecast,
            outflows=outflows_forecast,
            nfcf=nfcf_forecast
        )
    
    # ==========================================
    # LÓGICA DE SINCRONIZACIÓN
    # ==========================================

    def _sync_series(self, leader_map: Dict, follower_map: Dict, label: str) -> Tuple[pd.Series, pd.Series]:
        """
        Recorta el follower para que empiece en la misma fecha que el primer dato NO-CERO del leader.
        """
        # Convertir a Series con índice de fecha
        s_leader = self._to_pandas(leader_map)
        s_follower = self._to_pandas(follower_map)

        # Encontrar primer índice no-cero del líder
        non_zero_idx = s_leader[s_leader > 0].index
        
        if len(non_zero_idx) == 0:
            return s_leader, s_follower # Si todo es 0, devolvemos tal cual (se manejará como data insuficiente)

        start_date = non_zero_idx[0]
        logger.info(f"Sincronización {label}: Cortando historia antes de {start_date.date()}")

        # Cortar ambas series desde esa fecha
        # Usamos reindex para asegurar que el follower tenga las mismas fechas, rellenando con 0 si faltan
        s_leader_cut = s_leader[s_leader.index >= start_date]
        
        # Para el follower, cortamos lo viejo y alineamos fechas
        s_follower_cut = s_follower[s_follower.index >= start_date]
        
        # Aseguramos que ambas terminen igual (rellenar huecos intermedios)
        # Esto unifica el índice
        common_idx = s_leader_cut.index.union(s_follower_cut.index).sort_values()
        
        return s_leader_cut.reindex(common_idx, fill_value=0.0), s_follower_cut.reindex(common_idx, fill_value=0.0)

    def _to_pandas(self, data_map: Dict) -> pd.Series:
        if not data_map:
            return pd.Series(dtype=float)
        df = pd.DataFrame(list(data_map.items()), columns=['ds', 'y'])
        df['ds'] = pd.to_datetime(df['ds'])
        df = df.set_index('ds').sort_index()
        return df['y'].asfreq('MS', fill_value=0.0)
    
    # ==========================================
    # LÓGICA DE PROYECCIÓN (3 MODELOS)
    # ==========================================
    def _process_metric(self, values: pd.Series, horizon: int, label: str) -> Forecast.MetricForecast:
        n_obs = len(values)
        if n_obs < 3: # Mínimo absoluto para proyectar algo
            return Forecast.MetricForecast()

        # Generar fechas futuras
        last_date = values.index[-1]
        future_dates = pd.date_range(start=last_date, periods=horizon + 1, freq='MS')[1:]

        # --- CALCULAR METADATOS (Histórico) ---
        hist_growth = 0.0
        if n_obs >= 6:
            recent = values.iloc[-3:].mean()
            start = values.iloc[:3].mean()
            if start > 0: hist_growth = (recent - start) / start

        last_12_sum = values.iloc[-12:].sum() if n_obs >= 12 else values.sum() * (12/n_obs)

        # -------------------------------------------------------
        # 1. LINEAL (Slope puro) - Sin cambios, funciona bien
        # -------------------------------------------------------
        x = np.arange(n_obs)
        y = values.values
        A = np.vstack([x, np.ones(len(x))]).T
        m, c = np.linalg.lstsq(A, y, rcond=None)[0]
        
        x_future = np.arange(n_obs, n_obs + horizon)
        y_pred_lin = m * x_future + c
        
        residuals = y - (m * x + c)
        std_error = np.std(residuals)
        
        res_linear = self._build_model_result(
            y_pred_lin, std_error, future_dates, "Linear Regression (Slope)", hist_growth, last_12_sum
        )

        # -------------------------------------------------------
        # 2. EXPONENCIAL (Curva Suavizada) - FIX: Damping controlado
        # -------------------------------------------------------
        res_exp = None
        try:
            # FIX: Usamos damped_trend=True para dar curvatura.
            # 'damping_trend': 0.98 permite que la curva continúe subiendo/bajando 
            # pero se "canse" muy lentamente, evitando líneas rectas infinitas.
            model_exp = ExponentialSmoothing(
                values, 
                trend='add', 
                seasonal=None, 
                damped_trend=True, 
                initialization_method="estimated"
            ).fit(damping_trend=0.32) # Forzamos un damping suave (casi 1.0)
            
            y_pred_exp = model_exp.forecast(horizon).to_numpy()
            
            resid_exp = model_exp.resid
            std_error_exp = np.std(resid_exp) if len(resid_exp) > 0 else std_error

            res_exp = self._build_model_result(
                y_pred_exp, std_error_exp, future_dates, "Exponential (Damped Trend)", hist_growth, last_12_sum
            )
        except Exception as e:
            logger.warning(f"Exponential model failed for {label}: {e}")

        # -------------------------------------------------------
        # 3. ESTACIONAL (Holt-Winters) - FIX: Manejo de Zeros
        # -------------------------------------------------------
        res_sea = None
        if n_obs >= 24:
            try:
                # Intentamos capturar la estacionalidad aditiva.
                # Si hay muchos ceros, el modelo aditivo puede restar y llevar a <0.
                model_sea = ExponentialSmoothing(
                    values, 
                    trend='add', 
                    seasonal='add', 
                    seasonal_periods=12, 
                    damped_trend=True,
                    initialization_method="estimated"
                ).fit(damping_trend=0.90) # Damping un poco más fuerte para estacionalidad
                
                y_pred_sea = model_sea.forecast(horizon).to_numpy()
                
                # --- FIX Ceros Estacionales ---
                # Si el modelo predice CERO exacto repetidamente, a veces es mejor 
                # suavizarlo con un promedio móvil si detectamos colapso total.
                # Por ahora, confiamos en los datos, pero ten en cuenta que 
                # si en el pasado vendiste 0 en Agosto, el modelo predecirá 0 en Agosto.
                
                resid_sea = model_sea.resid
                std_error_sea = np.std(resid_sea) if len(resid_sea) > 0 else std_error

                res_sea = self._build_model_result(
                    y_pred_sea, std_error_sea, future_dates, "Holt-Winters Seasonal", hist_growth, last_12_sum
                )
            except Exception as e:
                logger.warning(f"Seasonal model failed for {label}: {e}")

        return Forecast.MetricForecast(
            linear=res_linear,
            exponential=res_exp,
            seasonal=res_sea
        )

    def _build_model_result(self, y_pred, std_error, dates, name, hist_growth, last_12_sum) -> Forecast.ModelResult:
        """
        Construye el objeto con los 3 escenarios y calcula sus 3 crecimientos individuales.
        """
        # Limpieza base (nada menor a 0)
        y_real = np.maximum(0, y_pred)
        
        # Incertidumbre (Banda constante)
        uncertainty = std_error 
        
        # Generar bandas
        y_opt = np.maximum(0, y_real + uncertainty)
        y_pess = np.maximum(0, y_real - uncertainty)

        # 1. GROWTH COMPARISON (Vs Historia)
        # Fórmula: (Suma Total Proyectada - Suma 12 Meses Previos) / Suma 12 Meses Previos
        def calc_comparison(arr_vals):
            total_pred = np.sum(arr_vals)
            if last_12_sum > 0:
                return (total_pred - last_12_sum) / last_12_sum
            return 0.0

        comp_real = calc_comparison(y_real)
        comp_opt = calc_comparison(y_opt)
        comp_pess = calc_comparison(y_pess)

        # 2. GROWTH PROJECTION (Tendencia Interna)
        # Fórmula: (Valor Mes 12 - Valor Mes 1) / Valor Mes 1
        # Nos dice si la curva va hacia arriba o hacia abajo en el futuro.
        def calc_internal_trend(arr_vals):
            if len(arr_vals) < 2: return 0.0
            start = arr_vals[0]
            end = arr_vals[-1]
            # Evitar división por cero
            if start > 1.0: 
                return (end - start) / start
            return 0.0

        trend_real = calc_internal_trend(y_real)
        trend_opt = calc_internal_trend(y_opt)
        trend_pess = calc_internal_trend(y_pess)

        # Mapear a objetos
        def to_pts(arr):
            return [Forecast.ForecastPoint(date=d.strftime("%Y-%m-%d"), value=round(float(v), 2)) for d, v in zip(dates, arr)]

        # Validación segura específica de cada escenario y de comparación y trend
        historical_growth_rate=round(hist_growth, 4) if hist_growth is not None else None
        comp_realistic=round(comp_real, 4) if comp_real is not None else None
        comp_optimistic=round(comp_opt, 4) if comp_opt is not None else None
        comp_pessimistic=round(comp_pess, 4) if comp_pess is not None else None

        trend_realistic=round(trend_real, 4) if trend_real is not None else None
        trend_optimistic=round(trend_opt, 4) if trend_opt is not None else None
        trend_pessimistic=round(trend_pess, 4) if trend_pess is not None else None

        return Forecast.ModelResult(
            scenarios=Forecast.Scenario(
                realistic=to_pts(y_real),
                optimistic=to_pts(y_opt),
                pessimistic=to_pts(y_pess)
            ),
            method_name=name,
            historical_growth_rate=historical_growth_rate,
            
            # Comparación vs histórico (últimos 12 meses)
            comparison_realistic=comp_realistic,
            comparison_optimistic=comp_optimistic,
            comparison_pessimistic=comp_pessimistic,

            # Tendencia interna de la proyección (Mes 12 vs Mes 1)
            trend_realistic=trend_realistic,
            trend_optimistic=trend_optimistic,
            trend_pessimistic=trend_pessimistic
        )

    # ==========================================
    # CÁLCULO DE NFCF (DERIVADO 3 ESCENARIOS)
    # ==========================================
    def _calculate_derived_nfcf(self, inflows: Forecast.MetricForecast, outflows: Forecast.MetricForecast) -> Forecast.MetricForecast:
        """
        Resta Inflows - Outflows para CADA modelo y CADA escenario.
        """
        nfcf_metric = Forecast.MetricForecast()

        # Helper para restar dos ModelResult
        def subtract_models(inf_mod: Forecast.ModelResult, out_mod: Forecast.ModelResult, name: str) -> Forecast.ModelResult:
            # Extraemos listas de puntos
            inf_scen = inf_mod.scenarios
            out_scen = out_mod.scenarios
            
            def sub_lists(l1, l2):
                return [Forecast.ForecastPoint(date=p1.date, value=round(p1.value - p2.value, 2)) for p1, p2 in zip(l1, l2)]

            # NFCF Realista = Inflow Real - Outflow Real
            # NFCF Optimista = Inflow Opt - Outflow Pess (Mejor caso: entra mucho, sale poco)
            # NFCF Pesimista = Inflow Pess - Outflow Opt (Peor caso: entra poco, sale mucho)
            
            return Forecast.ModelResult(
                scenarios=Forecast.Scenario(
                    realistic=sub_lists(inf_scen.realistic, out_scen.realistic),
                    optimistic=sub_lists(inf_scen.optimistic, out_scen.pessimistic),
                    pessimistic=sub_lists(inf_scen.pessimistic, out_scen.optimistic)
                ),
                method_name=name,
                historical_growth_rate=None, # No aplica igual
                growth_realistic=None,
                growth_optimistic=None,
                growth_pessimistic=None
            )

        # 1. Linear
        if inflows.linear and outflows.linear:
            nfcf_metric.linear = subtract_models(inflows.linear, outflows.linear, "Derived Linear (In-Out)")
        
        # 2. Exponential
        if inflows.exponential and outflows.exponential:
            nfcf_metric.exponential = subtract_models(inflows.exponential, outflows.exponential, "Derived Exponential (In-Out)")

        # 3. Seasonal
        if inflows.seasonal and outflows.seasonal:
            nfcf_metric.seasonal = subtract_models(inflows.seasonal, outflows.seasonal, "Derived Seasonal (In-Out)")

        return nfcf_metric