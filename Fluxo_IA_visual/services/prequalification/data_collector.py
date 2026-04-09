# Fluxo_IA_visual/services/prequalification/data_collector.py
import httpx
import asyncio
import logging
from typing import Dict, Any
from ...core.config import settings
from ..syntage_client import SyntageClient

logger = logging.getLogger(__name__)

class DataCollectorService:
    """
    Encargado exclusivamente de la recolección de datos (I/O Bound).
    Interactúa con SyntageClient para obtener todos los datos crudos usando concurrencia.
    """
    def __init__(self):
        api_key = settings.SYNTAGE_API_KEY.get_secret_value()
        self.client_repo = SyntageClient(api_key)

    async def fetch_all_raw_data(self, rfc: str) -> Dict[str, Any]:
        raw_data = {"rfc": rfc}
        
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            
            # --- OLA 1: Peticiones que solo dependen del RFC ---
            logger.debug(f"[{rfc}] Iniciando OLA 1: Ejecutando peticiones independientes concurrentemente...")
            (
                entity_details,
                activities,
                taxpayer_info,
                raw_cashflow,
                raw_sales,
                raw_expenditures,
                concentration_data,
                financial_tree,
                ciec_data,
                compliance_data
            ) = await asyncio.gather(
                self.client_repo.get_entity_detail(client, rfc),
                self.client_repo.get_tax_status(client, rfc),
                self.client_repo.get_taxpayer_info(client, rfc),
                self.client_repo.get_raw_monthly_data(client, rfc, "cash-flow"),
                self.client_repo.get_raw_monthly_data(client, rfc, "sales-revenue"),
                self.client_repo.get_raw_monthly_data(client, rfc, "expenditures"),
                self.client_repo.get_concentration_data(client, rfc),
                self.client_repo.get_financial_statements_tree(client, rfc),
                self.client_repo.get_ciec_status(client, rfc),
                self.client_repo.get_compliance_opinion(client, rfc)
            )

            # Desempaquetado y asignación de la OLA 1
            entity_id = entity_details.get("id")
            raw_data["entity_id"] = entity_id
            raw_data["registration_date"] = entity_details.get("registration_date")
            
            raw_data["activities"] = activities
            raw_data["taxpayer_name"] = taxpayer_info[0]
            raw_data["risks"] = taxpayer_info[1]
            
            raw_data["raw_cashflow"] = raw_cashflow
            raw_data["raw_sales"] = raw_sales
            raw_data["raw_expenditures"] = raw_expenditures
            
            raw_data["raw_clients"] = concentration_data[0]
            raw_data["raw_suppliers"] = concentration_data[1]
            raw_data["financial_tree"] = financial_tree
            
            raw_data["ciec_data"] = ciec_data
            raw_data["compliance_data"] = compliance_data

            # --- OLA 2: Peticiones que requieren el Entity ID ---
            if entity_id:
                async def fetch_pdf():
                    f_id = compliance_data.get("file_id") if isinstance(compliance_data, dict) else None
                    if f_id: return await self.client_repo.download_file_content(client, f_id)
                    return b""
                logger.debug(f"[{rfc}] Iniciando OLA 2: Ejecutando peticiones dependientes del Entity ID...")
                (
                    buro_data,
                    raw_customer_net,
                    raw_vendor_net,
                    raw_products_sold,
                    raw_products_bought,
                    raw_employees,
                    raw_blacklist,
                    raw_rpc,
                    raw_rug,
                    raw_compliance_pdf,
                    raw_sales_pue_ppd,
                    raw_accounts_rp,
                    raw_financial_institutions
                ) = await asyncio.gather(
                    self.client_repo.get_buro_report_status(client, entity_id, rfc),
                    self.client_repo.get_network_data(client, entity_id, "customer-network"),
                    self.client_repo.get_network_data(client, entity_id, "vendor-network"),
                    self.client_repo.get_products_and_services(client, entity_id, "sold"),
                    self.client_repo.get_products_and_services(client, entity_id, "bought"),
                    self.client_repo.get_employees_insight(client, entity_id),
                    self.client_repo.get_invoicing_blacklist(client, entity_id),
                    self.client_repo.get_rpc_records(client, entity_id),
                    self.client_repo.get_rug_records(client, entity_id),
                    fetch_pdf(),
                    self.client_repo.get_sales_pue_ppd(client, entity_id),
                    self.client_repo.get_accounts_receivable_payable(client, entity_id),
                    self.client_repo.get_financial_institutions(client, entity_id)
                )
                
                raw_data["buro_data"] = buro_data
                raw_data["raw_customer_net"] = raw_customer_net
                raw_data["raw_vendor_net"] = raw_vendor_net
                raw_data["raw_products_sold"] = raw_products_sold
                raw_data["raw_products_bought"] = raw_products_bought
                raw_data["raw_employees"] = raw_employees
                raw_data["raw_blacklist"] = raw_blacklist
                raw_data["raw_rpc"] = raw_rpc
                raw_data["raw_rug"] = raw_rug
                raw_data["raw_compliance_pdf"] = raw_compliance_pdf
                raw_data["raw_sales_pue_ppd"] = raw_sales_pue_ppd
                raw_data["raw_accounts_rp"] = raw_accounts_rp
                raw_data["raw_financial_institutions"] = raw_financial_institutions
            
                # --- OLA 3: Enriquecer Lista Negra con Montos de Facturas ---
                if raw_blacklist:
                    logger.debug(f"[{rfc}] Iniciando OLA 3: Obteniendo montos acumulados para Lista Negra...")
                    # Normalizamos el diccionario como lo tienes en el procesador
                    bl_dict = raw_blacklist[0] if isinstance(raw_blacklist, list) and len(raw_blacklist) > 0 else raw_blacklist
                    
                    if isinstance(bl_dict, dict):
                        tasks = []
                        task_meta = [] # Para saber a qué registro le toca cada resultado
                        
                        for category in ["issued", "received"]:
                            items = bl_dict.get(category, [])
                            if isinstance(items, list):
                                for item in items:
                                    c_rfc = item.get("taxpayer", {}).get("rfc")
                                    if c_rfc and c_rfc != "N/A":
                                        # Si está en 'issued', la empresa emitió la factura y la contraparte es el 'receiver'
                                        is_receiver = (category == "issued")
                                        
                                        # Preparamos la tarea concurrente
                                        tasks.append(
                                            self.client_repo.get_invoice_totals_by_rfc(client, entity_id, c_rfc, is_receiver)
                                        )
                                        task_meta.append(item) # Guardamos la referencia al diccionario original
                        
                        # Disparamos todas las sumas al mismo tiempo
                        if tasks:
                            resultados_montos = await asyncio.gather(*tasks)
                            # Inyectamos el resultado directamente en el diccionario crudo original
                            for meta_item, monto_total in zip(task_meta, resultados_montos):
                                meta_item["monto_acumulado"] = monto_total

            else:
                logger.warning(f"[{rfc}] Omitiendo OLA 2: No se encontró Entity ID.")
                raw_data["buro_data"] = {"status": "entity_not_found"}
                raw_data["raw_customer_net"] = []
                raw_data["raw_vendor_net"] = []
                raw_data["raw_products_sold"] = []
                raw_data["raw_products_bought"] = []
                raw_data["raw_employees"] = []
                raw_data["raw_blacklist"] = []
                raw_data["raw_rpc"] = []
                raw_data["raw_rug"] = []
                raw_data["raw_compliance_pdf"] = b""
                raw_data["raw_sales_pue_ppd"] = {}
                raw_data["raw_accounts_rp"] = {}
                raw_data["raw_financial_institutions"] = []

        return raw_data