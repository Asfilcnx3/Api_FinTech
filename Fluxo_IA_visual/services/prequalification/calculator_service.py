import logging
from ...models.responses_precalificacion import PrequalificationResponse

# Configuración de logger propio para cálculos
logger = logging.getLogger("financial_calculator")

class FinancialCalculatorService:
    """
    Servicio dedicado al cálculo de razones financieras y limpieza de datos contables.
    Aisla la lógica matemática de la extracción de datos.
    """

    def calculate_ratios_for_year(self, inputs: PrequalificationResponse.FinancialYearInput) -> PrequalificationResponse.FinancialRatioYear:
        """
        Toma los inputs crudos (con posibles cuentas separadas de utilidad/pérdida)
        y retorna el objeto final con los ratios calculados.
        """
        year = inputs.year
        logger.debug(f"--- Calculando Ratios para el Año {year} ---")

        # 1. RESOLUCIÓN DE SIGNOS
        gross_income = self._resolve_sign(inputs.gross_profit, inputs.gross_loss, "Gross Profit")
        net_income = self._resolve_sign(inputs.net_profit, inputs.net_loss, "Net Income")
        ebit = self._resolve_sign(inputs.ebit_profit, inputs.ebit_loss, "EBIT")
        ebt = self._resolve_sign(inputs.ebt_profit, inputs.ebt_loss, "EBT")

        # 2. ARITMÉTICA ESTRICTA
        
        # NOPAT = EBIT - Impuestos Reales
        # Si no hay impuestos (0), NOPAT es igual al EBIT.
        nopat = ebit - inputs.taxes

        # Reconstrucción opcional segura: Si hay Utilidad Neta e Impuestos, pero no EBT
        if ebt == 0 and net_income != 0:
            logger.debug(f"Year {year}: Reconstruyendo EBT desde NetIncome + Taxes")
            ebt = net_income + inputs.taxes

        # 3. CÁLCULO DE RAZONES
        # Aseguramos que COGS e Intereses sean absolutos para no alterar el sentido de las fórmulas
        cogs_abs = abs(inputs.cogs)
        interest_exp_abs = abs(inputs.interest_expense)

        # A) Liquidez
        current_ratio = self._safe_division(inputs.current_assets, inputs.current_liabilities)
        quick_ratio = self._safe_division(inputs.current_assets - inputs.inventory, inputs.current_liabilities)
        cash_ratio = self._safe_division(inputs.cash_and_equivalents, inputs.current_liabilities)

        # B) Rendimiento sobre la Inversión (ROI)
        roa = self._safe_division(net_income, inputs.assets)
        roe = self._safe_division(net_income, inputs.equity)
        margin_percent = self._safe_division(net_income, inputs.revenue) * 100
        # Formula Genérica: EBT / Activos. (Se cambiará después)
        roa_tax_strategy = self._safe_division(ebt, inputs.assets) 

        # C) Estructura de Capital y Solvencia
        leverage = self._safe_division(inputs.liabilities, inputs.equity)
        debt_ratio = self._safe_division(inputs.liabilities, inputs.assets)
        interest_coverage = self._safe_division(ebit, interest_exp_abs)

        # D) Flujo de Fondos
        ocf = inputs.operating_cash_flow
        cash_flow_coverage = self._safe_division(ocf, inputs.liabilities)
        working_capital = inputs.current_assets - inputs.current_liabilities

        # E) Desempeño Operativo
        dio = self._safe_division(inputs.inventory, cogs_abs) * 365
        dso = self._safe_division(inputs.accounts_receivable, inputs.revenue) * 365
        dpo = self._safe_division(inputs.accounts_payable, cogs_abs) * 365
        fixed_asset_turnover = self._safe_division(inputs.revenue, inputs.fixed_assets)
        total_asset_turnover = self._safe_division(inputs.revenue, inputs.assets)

        # F) Indicador de Altman (Z-Score para empresas privadas)
        t1 = self._safe_division(working_capital, inputs.assets)
        t2 = self._safe_division(inputs.retained_earnings, inputs.assets)
        t3 = self._safe_division(ebit, inputs.assets)
        t4 = self._safe_division(inputs.equity, inputs.liabilities)
        t5 = self._safe_division(inputs.revenue, inputs.assets)
        altman_z = (1.2 * t1) + (1.4 * t2) + (3.3 * t3) + (0.6 * t4) + (1.0 * t5)

        return PrequalificationResponse.FinancialRatioYear(
            year=year,
            
            # --- Ratios Originales y ROI ---
            roa=round(roa, 4),
            roe=round(roe, 4),
            net_profit_margin_percent=round(margin_percent, 2),
            roa_tax_strategy=round(roa_tax_strategy, 4),
            
            # --- Ratios Nuevos ---
            current_ratio=round(current_ratio, 2),
            quick_ratio=round(quick_ratio, 2),
            cash_ratio=round(cash_ratio, 2),
            
            leverage=round(leverage, 2),
            debt_ratio=round(debt_ratio, 4),
            interest_coverage=round(interest_coverage, 2),
            
            operating_cash_flow=round(ocf, 2),
            cash_flow_coverage=round(cash_flow_coverage, 2),
            working_capital=round(working_capital, 2),
            
            dio=round(dio, 1),
            dso=round(dso, 1),
            dpo=round(dpo, 1),
            fixed_asset_turnover=round(fixed_asset_turnover, 2),
            total_asset_turnover=round(total_asset_turnover, 2),
            altman_z_score=round(altman_z, 2),

            # --- Base e Inputs crudos ---
            ebit=round(ebit, 2),
            ebt=round(ebt, 2),
            nopat=round(nopat, 2),

            input_assets=round(inputs.assets, 2),
            input_liabilities=round(inputs.liabilities, 2),   
            input_equity=round(inputs.equity, 2),
            input_revenue=round(inputs.revenue, 2),
            input_gross_profit=round(gross_income, 2),        
            input_net_income=round(net_income, 2),
            input_taxes=round(inputs.taxes, 2),

            raw_net_profit=round(inputs.net_profit, 2),
            raw_net_loss=round(inputs.net_loss, 2),
            raw_ebit_profit=round(inputs.ebit_profit, 2),
            raw_ebit_loss=round(inputs.ebit_loss, 2),
            raw_ebt_profit=round(inputs.ebt_profit, 2),
            raw_ebt_loss=round(inputs.ebt_loss, 2)
        )

    # --- HELPERS PRIVADOS ---
    def _resolve_sign(self, profit_val: float, loss_val: float, label: str) -> float:
        """
        Determina el valor real basado en cuentas de Utilidad (Positiva) y Pérdida (Positiva conceptualmente negativa).
        """
        final_val = 0.0
        if profit_val != 0:
            final_val = profit_val
        elif loss_val > 0:
            final_val = -loss_val # Convertimos a negativo
            
        # Loguear solo si hay algo interesante (para no ensuciar logs con ceros)
        if final_val != 0:
            logger.debug(f"   > {label} resuelto: {final_val} (Profit: {profit_val}, Loss: {loss_val})")
            
        return final_val

    def _safe_division(self, numerator: float, denominator: float) -> float:
        """División segura para evitar ZeroDivisionError"""
        if denominator and denominator != 0:
            return numerator / denominator
        return 0.0