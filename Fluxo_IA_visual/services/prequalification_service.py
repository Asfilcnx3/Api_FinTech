from ..core.config import settings
from ..services.syntage_client import SyntageClient
from ..services.calculator_services import FinancialCalculatorService
from ..models.responses_precalificacion import PrequalificationResponse
from ..services.forecasting_service import ForecastingService
from datetime import datetime
from typing import List, Dict, Any, Tuple
import httpx
import statistics
import logging
import math # <--- Necesario para el CAGR

logger = logging.getLogger(__name__)

class PrequalificationService:
    """
    SERVICIO DE DOMINIO:
    Encargado de la lógica de negocio, orquestación de datos y transformación
    de respuestas para la precalificación financiera.
    """
    def __init__(self):
        # 1. Configuración de dependencias
        api_key = settings.SYNTAGE_API_KEY.get_secret_value()
        
        self.client_repo = SyntageClient(api_key)
        self.calculator = FinancialCalculatorService()
        self.forecaster = ForecastingService()

    async def analyze_taxpayer(self, rfc: str) -> PrequalificationResponse.PrequalificationFinalResponse:
        """
        Flujo principal que coordina toda la extracción y procesamiento.
        """
        async with httpx.AsyncClient() as client:
            # --- FASE 1: RECOLECCIÓN DE DATOS (I/O Bound) ---
            
            # 1. Datos básicos y Entidad (para ID y Fecha Registro)
            entity_details = await self.client_repo.get_entity_detail(client, rfc)
            entity_id = entity_details["id"] 
            reg_date = entity_details["registration_date"]
            
            # 2. Actividades Económicas
            activities = await self.client_repo.get_tax_status(client, rfc)

            # 3. Identidad y Riesgos (Usando tu lógica corregida de fecha)
            taxpayer_name, risks = await self.client_repo.get_taxpayer_info(client, rfc)
            
            # 4. Series de Tiempo
            raw_cashflow = await self.client_repo.get_raw_monthly_data(client, rfc, "cash-flow")
            raw_sales = await self.client_repo.get_raw_monthly_data(client, rfc, "sales-revenue")
            raw_expenditures = await self.client_repo.get_raw_monthly_data(client, rfc, "expenditures")
            
            # 5. Concentración
            raw_clients, raw_suppliers = await self.client_repo.get_concentration_data(client, rfc)
            
            # 6. Estados Financieros
            financial_tree = await self.client_repo.get_financial_statements_tree(client, rfc)
            
            # 7. Credenciales
            ciec_data = await self.client_repo.get_ciec_status(client, rfc) 
            # IMPORTANTE: Pasar entity_id si tu lógica de buró ya lo usa (sino rfc)
            buro_data = await self.client_repo.get_buro_report_status(client, entity_id, rfc) 
            compliance_data = await self.client_repo.get_compliance_opinion(client, rfc)

        # --- FASE 2: PROCESAMIENTO DE LÓGICA DE NEGOCIO (CPU Bound) ---
        
        # A. Procesamiento Temporal AVANZADO (AQUÍ ESTABA EL ERROR)
        # Reemplazamos _process_temporal_data con _calculate_advanced_stats
        stats_windows = self._calculate_advanced_stats(
            raw_cashflow, raw_sales, raw_expenditures
        )

        # B. Procesamiento de Concentración
        concentration_metrics = self._process_concentration(raw_clients, raw_suppliers)

        # C. Procesamiento Financiero
        financial_ratios = self._process_financial_statements(financial_tree)

        # --- FASE 3: PRONÓSTICO FINANCIERO INTEGRAL ---
        
        # Preparar mapas planos para Inflows/Outflows
        inflows_map = {}
        outflows_map = {}
        for date_key, vals in raw_cashflow.items():
            if isinstance(vals, dict):
                inflows_map[date_key] = vals.get("in", 0.0)
                outflows_map[date_key] = vals.get("out", 0.0)

        full_forecast = self.forecaster.generate_complete_forecast(
            revenue_map=raw_sales,
            expenditure_map=raw_expenditures,
            inflow_map=inflows_map,
            outflow_map=outflows_map,
            horizon=12
        )

        # --- FASE 4: CONSTRUCCIÓN DE RESPUESTA FINAL ---
        return PrequalificationResponse.PrequalificationFinalResponse(
            rfc=rfc,
            business_name=taxpayer_name,
            
            # Nuevos campos de perfil
            tax_registration_date=reg_date,
            economic_activities=[
                PrequalificationResponse.EconomicActivity(**act) for act in activities
            ],
            
            risk_indicators=risks,

            ciec_info=PrequalificationResponse.CredentialInfo(
                status=ciec_data["status"],
                last_check_date=ciec_data["date"]
            ),
            buro_info=PrequalificationResponse.BuroInfo(
                has_report=buro_data["has_report"],
                status=buro_data["status"],
                score=buro_data["score"],
                last_check_date=buro_data["date"]
            ),
            compliance_opinion=PrequalificationResponse.CredentialInfo(
                status=compliance_data["status"],
                last_check_date=compliance_data["date"]
            ),

            # AQUÍ ENTRA LA NUEVA ESTRUCTURA COMPLEJA
            stats_last_months=stats_windows,
            
            # Nota: Eliminé cashflow_current_month porque ya no lo usamos en el nuevo modelo
            # si aún lo necesitas, avísame, pero stats_windows cubre todo.
            
            concentration_last_12m=concentration_metrics,
            financial_ratios_history=financial_ratios,
            financial_predictions=full_forecast
        )

    # ==========================================
    # MÉTODOS PRIVADOS
    # ==========================================

    def _calculate_advanced_stats(self, cashflow_map, sales_map, exp_map) -> PrequalificationResponse.StatsWindows:
        """
        Calcula las métricas complejas (Mean, Slope, Median Growth, CAGR)
        para los periodos de auditoría: 3, 6, 9, 12, 24 meses.
        """
        # 1. Aplanar y ordenar datos
        sorted_keys = sorted(cashflow_map.keys()) # Ascendente cronológico
        
        data_points = []
        for k in sorted_keys:
            cf = cashflow_map[k]
            # Extraemos valores seguros
            rev = sales_map.get(k, 0.0)
            exp = exp_map.get(k, 0.0)
            inf = cf.get("in", 0.0) if isinstance(cf, dict) else 0.0
            out = cf.get("out", 0.0) if isinstance(cf, dict) else 0.0
            nfcf = inf - out
            
            data_points.append({
                "date": k, "revenue": rev, "expenditures": exp, 
                "inflows": inf, "outflows": out, "nfcf": nfcf
            })

        # Excluir mes actual (Regla de meses cerrados)
        current_month = datetime.now().strftime("%Y-%m")
        history = [d for d in data_points if d["date"] != current_month]

        # Helper interno para calcular un bloque
        def calc_group(months_count):
            if len(history) == 0:
                return None # O devolver objeto vacío
            
            # Tomamos la ventana (ej. últimos 3)
            # Si hay menos datos que 'months_count', tomamos lo que haya
            window = history[-months_count:] if len(history) >= months_count else history
            
            # Ventana Previa (para Median Growth)
            # ej. Si pides last_3, comparamos con los 3 anteriores a esos.
            prev_window = []
            if len(history) >= (len(window) * 2):
                start_prev = -(len(window) * 2)
                end_prev = -len(window)
                prev_window = history[start_prev:end_prev]
            
            # Función para calcular las 4 métricas de UNA métrica (ej. Revenue)
            def get_metrics(key):
                vals_curr = [x[key] for x in window]
                vals_prev = [x[key] for x in prev_window] if prev_window else []
                
                # A. MEAN
                mean_val = statistics.mean(vals_curr) if vals_curr else 0.0
                
                # B. MEDIAN GROWTH (Opción A: Median(Curr) vs Median(Prev))
                med_curr = statistics.median(vals_curr) if vals_curr else 0.0
                # Manejo de datos insuficientes
                # Si no hay ventana previa (porque el historial es corto), devolvemos None
                # en lugar de 0.0, para que el Excel no pinte "0.00%".
                med_growth = None 
                
                if prev_window: # Solo calculamos si EXISTE historia previa
                    med_prev = statistics.median(vals_prev)
                    if med_prev != 0:
                        med_growth = (med_curr - med_prev) / abs(med_prev)
                    else:
                        # Si el periodo anterior fue 0 absoluto y ahora tenemos ventas,
                        # matemáticamente es crecimiento infinito (1.0 = 100% como placeholder o None)
                        med_growth = 1.0 if med_curr > 0 else 0.0
                
                # C. SLOPE (Regresión Lineal Simple)
                slope = 0.0
                if len(vals_curr) > 1:
                    n = len(vals_curr)
                    xs = range(n)
                    ys = vals_curr
                    sum_x = sum(xs)
                    sum_y = sum(ys)
                    sum_xy = sum(x*y for x,y in zip(xs, ys))
                    sum_xx = sum(x*x for x in xs)
                    denominator = (n * sum_xx - sum_x * sum_x)
                    if denominator != 0:
                        slope = (n * sum_xy - sum_x * sum_y) / denominator

                # D. CAGR / CMGR
                cagr = 0.0
                if len(vals_curr) >= 2:
                    start_val = vals_curr[0]
                    end_val = vals_curr[-1]
                    
                    # Si start_val es 0 o negativo, CAGR se rompe o es engañoso.
                    # Manejo seguro:
                    if start_val > 0 and end_val > 0:
                        try:
                            periods = len(vals_curr)
                            # Si periodo < 12 meses -> CMGR (mensual) -> exponente 1/n
                            # Si periodo >= 12 meses -> CAGR (anual) -> exponente 1/(n/12)
                            years = periods / 12.0
                            exponent = 1.0 / periods if periods < 12 else 1.0 / years
                            
                            cagr = (end_val / start_val) ** exponent - 1
                        except: 
                            cagr = 0.0
                median_growth_rate=round(med_growth, 4) if med_growth is not None else None
                return PrequalificationResponse.AdvancedPeriodMetrics(
                    mean=round(mean_val, 2),
                    median_growth_rate=median_growth_rate,
                    linear_slope=round(slope, 2),
                    cagr_cmgr=round(cagr, 4)
                )

            return PrequalificationResponse.PeriodGroup(
                revenue=get_metrics("revenue"),
                expenditures=get_metrics("expenditures"),
                inflows=get_metrics("inflows"),
                outflows=get_metrics("outflows"),
                nfcf=get_metrics("nfcf")
            )

        return PrequalificationResponse.StatsWindows(
            last_24_months=calc_group(24),
            last_12_months=calc_group(12),
            last_9_months=calc_group(9),
            last_6_months=calc_group(6),
            last_3_months=calc_group(3)
        )

    def _process_concentration(self, clients: List[Dict], suppliers: List[Dict]) -> PrequalificationResponse.ConcentrationMetrics:
        """Transfoma datos crudos a modelos."""
        def to_model(items):
            return [
                PrequalificationResponse.ConcentrationItem(
                    name=i["name"],
                    rfc=i["rfc"],
                    total_amount=i["total_amount"],
                    percentage=i["percentage"]
                ) for i in items
            ]

        return PrequalificationResponse.ConcentrationMetrics(
            top_5_clients=to_model(clients),
            top_5_suppliers=to_model(suppliers)
        )

    def _process_financial_statements(self, tree: Dict[str, Any]) -> List[PrequalificationResponse.FinancialRatioYear]:
        """
        Extrae datos del árbol, unifica utilidades/pérdidas, calcula impuestos y genera ratios.
        """
        bs_tree = tree.get("balance_sheet", {})
        is_tree = tree.get("income_statement", {})

        # 1. Extracción de Datos Crudos (Usando el parser estático del cliente)
        # Usamos SyntageClient.parse_values_from_tree (método estático público)
        assets = SyntageClient.parse_values_from_tree(bs_tree, ["Activo", "Total Activo"])
        equity = SyntageClient.parse_values_from_tree(bs_tree, ["Capital Contable", "Total Capital"])
        revenue = SyntageClient.parse_values_from_tree(is_tree, ["Ingresos Netos", "Ventas netas", "Ingresos"])
        
        # Dual fields (Profit/Loss)
        net_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad neta", "Resultado Neto"])
        net_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida neta", "Pérdida del ejercicio"])
        
        ebit_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad de operación", "EBIT"])
        ebit_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida de operación"])
        
        ebt_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad antes de impuestos", "EBT"])
        ebt_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida antes de impuestos"])

        # 2. Determinar Años Válidos (Activos o Ventas > 0)
        valid_years = set()
        candidates = set(assets.keys()) | set(revenue.keys()) | set(ebit_profit.keys())
        
        for y in candidates:
            if abs(assets.get(y, 0)) > 1 or abs(revenue.get(y, 0)) > 1:
                valid_years.add(y)
        
        sorted_years = sorted(list(valid_years), reverse=True)[:3]
        results = []

        # 3. Cálculo de Impuestos y Ratios
        for year in sorted_years:
            # Consolidación de valores
            raw_net_p = net_profit.get(year, 0.0)
            raw_net_l = net_loss.get(year, 0.0)
            net_income = raw_net_p - raw_net_l
            
            raw_ebt_p = ebt_profit.get(year, 0.0)
            raw_ebt_l = ebt_loss.get(year, 0.0)
            ebt = raw_ebt_p - raw_ebt_l
            
            # Regla de Negocio: Cálculo Matemático de Impuestos
            calculated_taxes = round(ebt - net_income, 2)

            # Preparar input para la calculadora
            year_input = PrequalificationResponse.FinancialYearInput(
                year=year,
                assets=assets.get(year, 0.0),
                equity=equity.get(year, 0.0),
                revenue=revenue.get(year, 0.0),
                taxes=calculated_taxes,
                net_profit=raw_net_p,
                net_loss=raw_net_l,
                ebit_profit=ebit_profit.get(year, 0.0),
                ebit_loss=ebit_loss.get(year, 0.0),
                ebt_profit=raw_ebt_p,
                ebt_loss=raw_ebt_l
            )

            # Delegar cálculo final de ratios
            ratios = self.calculator.calculate_ratios_for_year(year_input)
            results.append(ratios)

        return results