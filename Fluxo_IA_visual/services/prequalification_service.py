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
        
        # Inyectamos los servicios auxiliares
        self.client_repo = SyntageClient(api_key)
        self.calculator = FinancialCalculatorService()

        # Iniciamos el servicio de forecasting
        self.forecaster = ForecastingService()

    async def analyze_taxpayer(self, rfc: str) -> PrequalificationResponse.PrequalificationFinalResponse:
        """
        Flujo principal que coordina toda la extracción y procesamiento.
        """
        async with httpx.AsyncClient() as client:
            # --- FASE 1: RECOLECCIÓN DE DATOS (I/O Bound) ---
            # Delegamos al cliente la tarea de ir a buscar los datos crudos
            
            # 1. Identidad y Riesgos
            taxpayer_name, risks = await self.client_repo.get_taxpayer_info(client, rfc)
            
            # 2. Series de Tiempo (Ingresos, Egresos, Ventas)
            raw_cashflow = await self.client_repo.get_raw_monthly_data(client, rfc, "cash-flow")
            raw_sales = await self.client_repo.get_raw_monthly_data(client, rfc, "sales-revenue")
            raw_expenditures = await self.client_repo.get_raw_monthly_data(client, rfc, "expenditures")
            
            # 3. Concentración (Clientes/Proveedores)
            raw_clients, raw_suppliers = await self.client_repo.get_concentration_data(client, rfc)
            
            # 4. Estados Financieros (Árbol JSON)
            financial_tree = await self.client_repo.get_financial_statements_tree(client, rfc)
            
            # 5. Credenciales y Cumplimiento (CIEC, Buró, Opinión 32-D)
            # Ejecutamos las 3 llamadas en paralelo para velocidad
            ciec_data = await self.client_repo.get_ciec_status(client, rfc) 
            buro_data = await self.client_repo.get_buro_report_status(client, rfc)
            compliance_data = await self.client_repo.get_compliance_opinion(client, rfc)

        # --- FASE 2: PROCESAMIENTO DE LÓGICA DE NEGOCIO (CPU Bound) ---
        
        # A. Procesamiento Temporal (Separar Mes Actual vs Histórico y calcular Stats)
        cashflow_metrics, current_month_metrics = self._process_temporal_data(
            raw_cashflow, raw_sales, raw_expenditures
        )

        # B. Procesamiento de Concentración (Convertir dicts a Modelos)
        concentration_metrics = self._process_concentration(raw_clients, raw_suppliers)

        # C. Procesamiento Financiero (Parsing de árbol y cálculo de ratios)
        financial_ratios = self._process_financial_statements(financial_tree)

        # --- FASE 3: PRONÓSTICO DE VENTAS (CPU Bound) ---
        # Usamos los datos crudos de ventas ("sales-revenue")
        # El forecaster se encarga de ordenarlos y rellenar huecos.
        sales_forecast = self.forecaster.generate_forecast(
            historical_map=raw_sales,
            horizon=12  # Confirmamos horizonte de 12 meses
        )

        # Si la API no devolvió fecha de cumplimiento, usamos la fecha de la CIEC
        final_compliance_date = compliance_data["date"]
        if not final_compliance_date and compliance_data["status"] != "not_found":
            # Asumimos: Si tenemos opinión (positiva/negativa), se generó cuando corrió la CIEC.
            final_compliance_date = ciec_data["date"]

        # --- FASE 4: CONSTRUCCIÓN DE RESPUESTA FINAL ---
        return PrequalificationResponse.PrequalificationFinalResponse(
            rfc=rfc,
            business_name=taxpayer_name,
            risk_indicators=risks,

            # Mapeo de credenciales (ciec, buro y opinión de cumplimiento)
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
                last_check_date=final_compliance_date
            ),

            stats_last_months=cashflow_metrics,
            cashflow_current_month=current_month_metrics,
            concentration_last_12m=concentration_metrics,
            financial_ratios_history=financial_ratios,
            sales_forecast=sales_forecast
        )

    # ==========================================
    #      MÉTODOS PRIVADOS (LÓGICA PURA)
    # ==========================================

    def _process_temporal_data(
        self, 
        cashflow_map: Dict[str, Any], 
        sales_map: Dict[str, float], 
        exp_map: Dict[str, float]
    ) -> Tuple[PrequalificationResponse.StatsWindows, PrequalificationResponse.CurrentMonthMetrics]:
        """
        Lógica para separar el mes en curso (incompleto) de los 12 meses históricos cerrados.
        Calcula estadísticas (media/mediana) sobre los meses cerrados.
        """
        current_month_key = datetime.now().strftime("%Y-%m")
        
        # Listas para almacenar historia (Ahora soportan hasta 24+ meses)
        history = { "in": [], "out": [], "nfcf": [], "sales": [], "exp": [] }
        curr = { "in": 0.0, "out": 0.0, "nfcf": 0.0, "sales": 0.0, "exp": 0.0 }

        sorted_keys = sorted(cashflow_map.keys(), reverse=True)
        count_closed = 0

        for date_key in sorted_keys:
            # Los datos ya vienen normalizados del cliente (YYYY-MM), no hace falta normalizar aquí de nuevo
            # a menos que el cliente fallara, pero asumimos contrato limpio.
            
            # Extraemos valores cashflow
            cf_node = cashflow_map[date_key]
            val_in = cf_node["in"]
            val_out = cf_node["out"]
            val_nfcf = val_in - val_out
            
            # Buscamos valores correspondientes en sales/exp (si existen para esa fecha)
            val_sales = sales_map.get(date_key, 0.0)
            val_exp = exp_map.get(date_key, 0.0)

            if date_key == current_month_key:
                # Es el mes actual
                curr["in"], curr["out"], curr["nfcf"] = val_in, val_out, val_nfcf
                curr["sales"], curr["exp"] = val_sales, val_exp
            else:
                # Aumentamos el buffer de memoria a 24 meses
                if count_closed < 24: 
                    history["in"].append(val_in)
                    history["out"].append(val_out)
                    history["nfcf"].append(val_nfcf)
                    history["sales"].append(val_sales)
                    history["exp"].append(val_exp)
                    count_closed += 1

        # Helper reutilizable (sin cambios, la magia del slicing lo hace todo)
        def calculate_metrics_for_window(months_limit: int) -> PrequalificationResponse.CashflowMetrics:
            # Si pedimos 24 meses y solo hay 14, Python usa los 14 disponibles automáticamente.
            return PrequalificationResponse.CashflowMetrics(
                inflows_stats=self._calculate_stats(history["in"][:months_limit]),
                outflows_stats=self._calculate_stats(history["out"][:months_limit]),
                nfcf_stats=self._calculate_stats(history["nfcf"][:months_limit]),
                expenditures_stats=self._calculate_stats(history["exp"][:months_limit]),
                sales_revenue_stats=self._calculate_stats(history["sales"][:months_limit])
            )

        # Construcción del objeto expandido
        stats_windows = PrequalificationResponse.StatsWindows(
            last_3_months=calculate_metrics_for_window(3),
            last_6_months=calculate_metrics_for_window(6),
            last_12_months=calculate_metrics_for_window(12),
            last_16_months=calculate_metrics_for_window(16),
            last_18_months=calculate_metrics_for_window(18),
            last_24_months=calculate_metrics_for_window(24)
        )

        current_metrics = PrequalificationResponse.CurrentMonthMetrics(
            month=current_month_key,
            inflows=round(curr["in"], 2),
            outflows=round(curr["out"], 2),
            nfcf=round(curr["nfcf"], 2),
            sales_revenue=round(curr["sales"], 2),
            expenditures=round(curr["exp"], 2)
        ) if current_month_key in cashflow_map else None

        return stats_windows, current_metrics

    def _process_concentration(self, clients: List[Dict], suppliers: List[Dict]) -> PrequalificationResponse.ConcentrationMetrics:
        """
        Transforma diccionarios crudos en modelos Pydantic.
        """
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

    def _calculate_stats(self, values: List[float]) -> PrequalificationResponse.Stats:
        """Helper para calcular media y mediana."""
        if not values:
            return PrequalificationResponse.Stats(mean=0.0, median=0.0)
        return PrequalificationResponse.Stats(
            mean=round(statistics.mean(values), 2),
            median=round(statistics.median(values), 2)
        )