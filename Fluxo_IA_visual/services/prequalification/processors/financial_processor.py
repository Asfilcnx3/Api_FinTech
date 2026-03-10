# Fluxo_IA_visual/services/prequalification/processors/financial_processor.py
from typing import Dict, Any, List
import logging
import statistics
from datetime import datetime
from ....models.responses_precalificacion import PrequalificationResponse
from ...syntage_client import SyntageClient
from ..calculator_service import FinancialCalculatorService

logger = logging.getLogger(__name__)

class FinancialProcessor:
    """
    Procesa matemáticas financieras: Estados Financieros, Ratios y Series de Tiempo (Stats).
    """
    def __init__(self):
        self.calculator = FinancialCalculatorService()

    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Finanzas y Series de Tiempo...")
        
        raw_cashflow = raw_data.get("raw_cashflow", {})
        raw_sales = raw_data.get("raw_sales", {})
        raw_expenditures = raw_data.get("raw_expenditures", {})
        financial_tree = raw_data.get("financial_tree", {})
        
        # 1. Stats Avanzados (Medias, CAGR, Slope)
        stats_windows = self._calculate_advanced_stats(raw_cashflow, raw_sales, raw_expenditures)
        
        # 2. Árbol Financiero y Ratios
        financial_ratios = self._process_financial_statements(financial_tree)
        
        # 3. Preparación Histórica para Forecaster y Excel (Raw Data)
        raw_history_list, simple_sales, simple_exp, simple_in, simple_out = self._prepare_time_series(
            raw_cashflow, raw_sales, raw_expenditures
        )
        
        return {
            "stats_last_months": stats_windows,
            "financial_ratios_history": financial_ratios,
            "financial_statements_tree": financial_tree,
            "raw_data_history": raw_history_list,
            
            # Mapas simples requeridos por el orquestador para inyectar al forecaster
            "simple_sales": simple_sales,
            "simple_exp": simple_exp,
            "simple_in": simple_in,
            "simple_out": simple_out
        }

    # =========================================================
    # LÓGICAS INTERNAS (Copiadas tal cual de tu versión anterior)
    # =========================================================
    
    def _prepare_time_series(self, raw_cashflow, raw_sales, raw_expenditures):
        """Aplana la serie de tiempo para el excel y para el forecaster."""
        all_dates = set(raw_cashflow.keys()) | set(raw_sales.keys()) | set(raw_expenditures.keys())
        sorted_dates = sorted(list(all_dates))
        
        raw_history_list = []
        simple_sales, simple_exp, simple_in, simple_out = {}, {}, {}, {}

        for d in sorted_dates:
            s_obj = raw_sales.get(d, {"amount": 0.0, "count": 0})
            e_obj = raw_expenditures.get(d, {"amount": 0.0, "count": 0})
            cf_obj = raw_cashflow.get(d, {
                "in": {"amount": 0.0, "count": 0}, 
                "out": {"amount": 0.0, "count": 0}
            })
            
            rev = float(s_obj["amount"])
            exp = float(e_obj["amount"])
            inf_amt = float(cf_obj["in"]["amount"])
            out_amt = float(cf_obj["out"]["amount"])
            nfcf = inf_amt - out_amt 
            
            inf_cnt = int(cf_obj["in"].get("count", 0))
            out_cnt = int(cf_obj["out"].get("count", 0))
            
            raw_history_list.append(PrequalificationResponse.RawDataPoint(
                date=d, revenue=rev, expenses=exp,
                inflows_amount=inf_amt, outflows_amount=out_amt, nfcf=nfcf,
                inflows_count=inf_cnt, outflows_count=out_cnt
            ))

            simple_sales[d] = rev
            simple_exp[d] = exp
            simple_in[d] = inf_amt
            simple_out[d] = out_amt
            
        return raw_history_list, simple_sales, simple_exp, simple_in, simple_out

    def _process_financial_statements(self, tree: Dict[str, Any]) -> List[PrequalificationResponse.FinancialRatioYear]:
        """Extrae el árbol usando métodos del cliente y lo pasa a la calculadora."""
        bs_tree = tree.get("balance_sheet", {})
        is_tree = tree.get("income_statement", {})

        assets = SyntageClient.parse_values_from_tree(bs_tree, ["Activo", "Total Activo"])
        liabilities = SyntageClient.parse_values_from_tree(bs_tree, ["Pasivo", "Total Pasivo"])
        equity = SyntageClient.parse_values_from_tree(bs_tree, ["Capital Contable", "Total Capital", "Capital"])
        
        revenue = SyntageClient.parse_values_from_tree(is_tree, ["Ingresos Netos", "Ventas netas", "Ingresos"])
        gross_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad Bruta"])
        gross_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida Bruta"])
        
        net_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad neta", "Resultado Neto"])
        net_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida neta", "Pérdida del ejercicio"])
        ebit_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad de operación", "EBIT"])
        ebit_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida de operación"])
        ebt_profit = SyntageClient.parse_values_from_tree(is_tree, ["Utilidad antes de impuestos", "EBT"])
        ebt_loss = SyntageClient.parse_values_from_tree(is_tree, ["Pérdida antes de impuestos"])

        valid_years = set()
        candidates = set(assets.keys()) | set(revenue.keys()) | set(ebit_profit.keys())
        for y in candidates:
            if abs(assets.get(y, 0)) > 1 or abs(revenue.get(y, 0)) > 1:
                valid_years.add(y)
        
        sorted_years = sorted(list(valid_years), reverse=True)[:3]
        results = []

        for year in sorted_years:
            raw_net_p = net_profit.get(year, 0.0)
            raw_net_l = net_loss.get(year, 0.0)
            net_income = raw_net_p - raw_net_l
            
            raw_ebt_p = ebt_profit.get(year, 0.0)
            raw_ebt_l = ebt_loss.get(year, 0.0)
            ebt = raw_ebt_p - raw_ebt_l
            
            calculated_taxes = round(ebt - net_income, 2)

            year_input = PrequalificationResponse.FinancialYearInput(
                year=year,
                assets=assets.get(year, 0.0),
                liabilities=liabilities.get(year, 0.0),
                equity=equity.get(year, 0.0),
                revenue=revenue.get(year, 0.0),
                taxes=calculated_taxes,
                gross_profit=gross_profit.get(year, 0.0),
                gross_loss=gross_loss.get(year, 0.0),
                net_profit=raw_net_p,
                net_loss=raw_net_l,
                ebit_profit=ebit_profit.get(year, 0.0),
                ebit_loss=ebit_loss.get(year, 0.0),
                ebt_profit=raw_ebt_p,
                ebt_loss=raw_ebt_l
            )
            ratios = self.calculator.calculate_ratios_for_year(year_input)
            results.append(ratios)

        return results

    def _calculate_advanced_stats(self, cashflow_map, sales_map, exp_map) -> PrequalificationResponse.StatsWindows:
        # 1. Aplanar y ordenar datos
        sorted_keys = sorted(cashflow_map.keys())
        data_points = []
        for k in sorted_keys:
            s_data = sales_map.get(k, {"amount": 0.0})
            rev = float(s_data.get("amount", 0.0)) if isinstance(s_data, dict) else float(s_data)

            e_data = exp_map.get(k, {"amount": 0.0})
            exp = float(e_data.get("amount", 0.0)) if isinstance(e_data, dict) else float(e_data)

            cf = cashflow_map[k]
            inf_data = cf.get("in", {"amount": 0.0})
            inf = float(inf_data.get("amount", 0.0)) if isinstance(inf_data, dict) else float(inf_data)

            out_data = cf.get("out", {"amount": 0.0})
            out = float(out_data.get("amount", 0.0)) if isinstance(out_data, dict) else float(out_data)

            nfcf = inf - out
            data_points.append({
                "date": k, "revenue": rev, "expenditures": exp, 
                "inflows": inf, "outflows": out, "nfcf": nfcf
            })

        current_month = datetime.now().strftime("%Y-%m")
        history = [d for d in data_points if d["date"] != current_month]

        def calc_group(months_count):
            if len(history) == 0: return None
            
            window = history[-months_count:] if len(history) >= months_count else history
            prev_window = []
            if len(history) >= (len(window) * 2):
                start_prev = -(len(window) * 2)
                end_prev = -len(window)
                prev_window = history[start_prev:end_prev]
            
            def get_metrics(key):
                vals_curr = [x[key] for x in window]
                vals_prev = [x[key] for x in prev_window] if prev_window else []
                
                mean_val = statistics.mean(vals_curr) if vals_curr else 0.0
                median_val = statistics.median(vals_curr) if vals_curr else 0.0
                
                sum_curr = sum(vals_curr)
                sum_prev = sum(vals_prev) if prev_window else 0.0
                
                period_growth = None 
                if prev_window:
                    if sum_prev != 0:
                        period_growth = (sum_curr - sum_prev) / abs(sum_prev)
                    else:
                        period_growth = 1.0 if sum_curr > 0 else 0.0

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

                cagr = 0.0
                if len(vals_curr) >= 2:
                    start_val = vals_curr[0]
                    end_val = vals_curr[-1]
                    if start_val > 0 and end_val > 0:
                        try:
                            periods = len(vals_curr)
                            years = periods / 12.0
                            exponent = 1.0 / periods if periods < 12 else 1.0 / years
                            cagr = (end_val / start_val) ** exponent - 1
                        except: 
                            cagr = 0.0
                
                period_growth_rate = round(period_growth, 4) if period_growth is not None else None
                
                return PrequalificationResponse.AdvancedPeriodMetrics(
                    mean=round(mean_val, 2),
                    median=round(median_val, 2),
                    period_growth_rate=period_growth_rate,
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