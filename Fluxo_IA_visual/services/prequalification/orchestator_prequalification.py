# Fluxo_IA_visual/services/prequalification/orchestator_prequalification.py
import logging
from ...models.responses_precalificacion import PrequalificationResponse
from .data_collector import DataCollectorService
from .forecasting_service import ForecastingService

# Estos procesadores los crearemos en el siguiente paso
from .processors.financial_processor import FinancialProcessor
from .processors.risk_processor import RiskProcessor
from .processors.network_processor import NetworkProcessor
from .processors.products_processor import ProductsProcessor
from .processors.registry_processor import RegistryProcessor

logger = logging.getLogger(__name__)

class PrequalificationOrchestrator:
    """
    MOTOR PRINCIPAL DE LÓGICA:
    Coordina el Data Collector, ejecuta los Procesadores por dominio y ensambla la respuesta.
    """
    def __init__(self):
        self.collector = DataCollectorService()
        self.risk_processor = RiskProcessor()
        self.financial_processor = FinancialProcessor()
        self.network_processor = NetworkProcessor()
        self.products_processor = ProductsProcessor()
        self.registry_processor = RegistryProcessor()
        self.forecaster = ForecastingService()

    async def analyze_taxpayer(self, rfc: str) -> PrequalificationResponse.PrequalificationFinalResponse:
        
        # --- FASE 1: RECOLECCIÓN (I/O Bound) ---
        logger.info(f"[{rfc}] FASE 1: Recolectando datos crudos...")
        raw_data = await self.collector.fetch_all_raw_data(rfc)

        # --- FASE 2: PROCESAMIENTO (CPU Bound) ---
        logger.info(f"[{rfc}] FASE 2: Ejecutando procesadores de dominio...")
        
        # A. Riesgos, Buró y Credenciales
        risk_payload = await self.risk_processor.process(raw_data)
        
        # B. Redes de Negocios y Concentración
        network_payload = self.network_processor.process(raw_data)
        
        # C. Métricas Financieras y Ratios (incluye preparación de datos para Forecaster)
        financial_payload = self.financial_processor.process(raw_data)

        # D. Productos y Servicios Vendidos/Comprados
        products_payload = await self.products_processor.process(raw_data)

        # E. Registros Públicos (RPC y RUG)
        registry_payload = self.registry_processor.process(raw_data)

        # --- FASE 3: PRONÓSTICOS ---
        logger.info(f"[{rfc}] FASE 3: Generando predicciones financieras...")
        forecast = self.forecaster.generate_complete_forecast(
            revenue_map=financial_payload["simple_sales"],
            expenditure_map=financial_payload["simple_exp"],
            inflow_map=financial_payload["simple_in"],
            outflow_map=financial_payload["simple_out"],
            horizon=12
        )

        # --- FASE 4: ENSAMBLAJE FINAL ---
        logger.info(f"[{rfc}] FASE 4: Construyendo respuesta final.")
        
        return PrequalificationResponse.PrequalificationFinalResponse(
            rfc=rfc,
            business_name=raw_data["taxpayer_name"],
            tax_registration_date=raw_data["registration_date"],
            
            # Desempaquetamos los resultados de los procesadores
            **risk_payload,
            **network_payload,
            **products_payload,
            **registry_payload,
            
            # Desempaquetamos finanzas (excluyendo los mapas simples temporales usados para el forecaster)
            stats_last_months=financial_payload["stats_last_months"],
            financial_ratios_history=financial_payload["financial_ratios_history"],
            financial_statements_tree=financial_payload["financial_statements_tree"],
            raw_data_history=financial_payload["raw_data_history"],
            accounts_receivable_payable=financial_payload["accounts_receivable_payable"],
            
            financial_predictions=forecast
        )