# Fluxo_IA_visual/services/prequalification/data_collector.py
import httpx
import logging
from typing import Dict, Any
from ...core.config import settings
from ..syntage_client import SyntageClient

logger = logging.getLogger(__name__)

class DataCollectorService:
    """
    Encargado exclusivamente de la recolección de datos (I/O Bound).
    Interactúa con SyntageClient para obtener todos los datos crudos.
    """
    def __init__(self):
        api_key = settings.SYNTAGE_API_KEY.get_secret_value()
        self.client_repo = SyntageClient(api_key)

    async def fetch_all_raw_data(self, rfc: str) -> Dict[str, Any]:
        raw_data = {"rfc": rfc}
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            # 1. Detalles Base
            entity_details = await self.client_repo.get_entity_detail(client, rfc)
            entity_id = entity_details.get("id")
            raw_data["entity_id"] = entity_id
            raw_data["registration_date"] = entity_details.get("registration_date")
            
            # 2. Información General
            raw_data["activities"] = await self.client_repo.get_tax_status(client, rfc)
            taxpayer_name, risks = await self.client_repo.get_taxpayer_info(client, rfc)
            raw_data["taxpayer_name"] = taxpayer_name
            raw_data["risks"] = risks
            
            # 3. Series de Tiempo
            raw_data["raw_cashflow"] = await self.client_repo.get_raw_monthly_data(client, rfc, "cash-flow")
            raw_data["raw_sales"] = await self.client_repo.get_raw_monthly_data(client, rfc, "sales-revenue")
            raw_data["raw_expenditures"] = await self.client_repo.get_raw_monthly_data(client, rfc, "expenditures")
            
            # 4. Concentración y Árboles
            clients, suppliers = await self.client_repo.get_concentration_data(client, rfc)
            raw_data["raw_clients"] = clients
            raw_data["raw_suppliers"] = suppliers
            raw_data["financial_tree"] = await self.client_repo.get_financial_statements_tree(client, rfc)
            
            # 5. Credenciales y Buró
            raw_data["ciec_data"] = await self.client_repo.get_ciec_status(client, rfc)
            raw_data["buro_data"] = await self.client_repo.get_buro_report_status(client, entity_id, rfc) if entity_id else {"status": "entity_not_found"}
            raw_data["compliance_data"] = await self.client_repo.get_compliance_opinion(client, rfc)
            
            # 6. Redes de Negocios
            if entity_id:
                raw_data["raw_customer_net"] = await self.client_repo.get_network_data(client, entity_id, "customer-network")
                raw_data["raw_vendor_net"] = await self.client_repo.get_network_data(client, entity_id, "vendor-network")
                raw_data["raw_products_sold"] = await self.client_repo.get_products_and_services(client, entity_id, "sold")
                raw_data["raw_products_bought"] = await self.client_repo.get_products_and_services(client, entity_id, "bought")
            else:
                raw_data["raw_customer_net"] = []
                raw_data["raw_vendor_net"] = []
                raw_data["raw_products_sold"] = []
                raw_data["raw_products_bought"] = []

        return raw_data