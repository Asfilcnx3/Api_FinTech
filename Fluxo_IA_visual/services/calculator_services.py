import logging
from ..models.responses_precalificacion import PrequalificationResponse

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
        logger.info(f"--- Calculando Ratios para el Año {year} ---")

        # 1. RESOLUCIÓN DE SIGNOS (Profit vs Loss)
        # Unificamos las cuentas separadas en una sola variable con el signo correcto.
        
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
        roa = self._safe_division(net_income, inputs.assets)
        roe = self._safe_division(net_income, inputs.equity)
        margin_percent = self._safe_division(net_income, inputs.revenue) * 100

        # Logs finales de los valores calculados
        logger.info(
            f"RESULTADOS {year}: "
            f"NetIncome={net_income:.2f} | EBIT={ebit:.2f} | NOPAT={nopat:.2f} | "
            f"ROA={roa:.4f} | ROE={roe:.4f} | Margin={margin_percent:.2f}%"
        )

        return PrequalificationResponse.FinancialRatioYear(
            # Ratios Calculados
            year=year,
            roa=round(roa, 4),
            roe=round(roe, 4),
            net_profit_margin_percent=round(margin_percent, 2),
            ebit=round(ebit, 2),
            ebt=round(ebt, 2),
            nopat=round(nopat, 2),
            
            # Datos Crudos (Evidencia)
            input_assets=round(inputs.assets, 2),
            input_equity=round(inputs.equity, 2),
            input_revenue=round(inputs.revenue, 2),
            input_net_income=round(net_income, 2), # Retornamos el valor ya con signo resuelto
            input_taxes=round(inputs.taxes, 2)
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