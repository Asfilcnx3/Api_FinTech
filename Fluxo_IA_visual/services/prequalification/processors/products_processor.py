# Fluxo_IA_visual/services/prequalification/processors/products_processor.py
from typing import Dict, Any, List
import logging
from ....models.responses_precalificacion import PrequalificationResponse
from ...ia_extractor import analizar_productos_y_tendencias_llm

logger = logging.getLogger(__name__)

class ProductsProcessor:
    """
    Procesa el catálogo de productos y servicios vendidos y comprados,
    e incluye un análisis de congruencia y tendencias con Inteligencia Artificial.
    """
    async def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Productos y Servicios con IA...")
        
        raw_sold = raw_data.get("raw_products_sold", [])
        raw_bought = raw_data.get("raw_products_bought", [])
        activities = raw_data.get("activities", [])
        
        # 1. Mapeo normal para el Excel
        sold_items = self._map_items(raw_sold)
        bought_items = self._map_items(raw_bought)

        # 2. Armar el paquete para la IA (Solo Top 10 para no volar tokens)
        payload_ia = {
            "actividades_economicas": [act.get("name") for act in activities if isinstance(act, dict)],
            "top_10_vendidos": self._extract_top_for_ia(raw_sold),
            "top_10_comprados": self._extract_top_for_ia(raw_bought)
        }

        # 3. Disparar el LLM
        analisis_ia = await analizar_productos_y_tendencias_llm(payload_ia)
        
        products_data = PrequalificationResponse.ProductsData(
            sold=sold_items,
            bought=bought_items,
            llm_activity_analysis=analisis_ia.get("analisis_actividad_redflags", "No se detectaron red flags o hubo un error en el análisis."),
            llm_trend_analysis=analisis_ia.get("analisis_tendencia_insumos", "No se detectaron tendencias o hubo un error en el análisis.")
        )
        
        return {
            "products_data": products_data
        }

    def _extract_top_for_ia(self, raw_list: Any, limit: int = 10) -> List[Dict]:
        """Extrae de forma limpia el nombre, monto y la línea de tiempo para la IA"""
        if not isinstance(raw_list, list): return []
        
        # Aseguramos que estén ordenados por monto mayor
        sorted_list = sorted(raw_list, key=lambda x: float(x.get("total", 0) if isinstance(x, dict) else 0), reverse=True)
        top = []
        
        for item in sorted_list[:limit]:
            if not isinstance(item, dict): continue
            desc = item.get("name") or item.get("description") or "Sin descripción"
            trans_crudas = item.get("transactions", [])
            
            # Limpiamos las transacciones para dejar solo fecha y dinero
            trans_resumidas = []
            if isinstance(trans_crudas, list):
                for t in trans_crudas:
                    if isinstance(t, dict):
                        trans_resumidas.append({"fecha": t.get("date"), "monto": t.get("total")})
                        
            top.append({
                "producto": desc,
                "monto_total": item.get("total", 0),
                "transacciones_mensuales": trans_resumidas
            })
        return top

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
            
            # Transacciones (si es lista sacamos len, si es int lo pasamos)
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