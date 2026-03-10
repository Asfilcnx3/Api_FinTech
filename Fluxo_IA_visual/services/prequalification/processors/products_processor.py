# Fluxo_IA_visual/services/prequalification/processors/products_processor.py
from typing import Dict, Any, List
import logging
from ....models.responses_precalificacion import PrequalificationResponse

logger = logging.getLogger(__name__)

class ProductsProcessor:
    """
    Procesa el catálogo de productos y servicios vendidos y comprados.
    """
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Productos y Servicios...")
        
        raw_sold = raw_data.get("raw_products_sold", [])
        # logger.info(f"Log debug - Raw Sold: {raw_sold}")
        raw_bought = raw_data.get("raw_products_bought", [])
        # logger.info(f"Log debug - Raw Sold: {raw_bought}")
        
        products_data = PrequalificationResponse.ProductsData(
            sold=self._map_items(raw_sold),
            bought=self._map_items(raw_bought)
        )
        
        return {
            "products_data": products_data
        }

    def _map_items(self, raw_list: Any) -> List[PrequalificationResponse.ProductServiceItem]:
        items = []
        if not isinstance(raw_list, list):
            return items
            
        for item in raw_list:
            desc = item.get("name") or item.get("description") or "Sin descripción"
            code = item.get("productCode") or item.get("code") or "N/A"
            
            try: total = float(item.get("total", 0.0))
            except: total = 0.0
            
            try: share = float(item.get("share") or item.get("percentage") or 0.0)
            except: share = 0.0
            
            # Si transactions es una lista (como vimos en el log), guardamos la longitud.
            # Si es un int (como en otros endpoints de Syntage), lo dejamos así.
            raw_trans = item.get("transactions")
            if isinstance(raw_trans, list):
                trans = len(raw_trans)
            else:
                try: trans = int(raw_trans or 0)
                except: trans = 0
            
            items.append(PrequalificationResponse.ProductServiceItem(
                description=str(desc),
                sat_code=str(code),
                total_amount=total,
                percentage=share,
                transactions=trans
            ))
            
        return items