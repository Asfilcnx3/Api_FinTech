# Concentración, Redes de Clientes/Proveedores# Fluxo_IA_visual/services/prequalification/processors/network_processor.py
from typing import Dict, Any, List
import logging
from datetime import datetime
from ....models.responses_precalificacion import PrequalificationResponse

logger = logging.getLogger(__name__)

class NetworkProcessor:
    """
    Procesa la concentración comercial y las redes de clientes/proveedores.
    """
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Redes y Concentración...")
        
        # 1. Concentración (Top 5)
        raw_clients = raw_data.get("raw_clients", [])
        raw_suppliers = raw_data.get("raw_suppliers", [])
        
        concentration = PrequalificationResponse.ConcentrationMetrics(
            top_5_clients=[self._to_concentration_item(i) for i in raw_clients],
            top_5_suppliers=[self._to_concentration_item(i) for i in raw_suppliers]
        )
        
        # 2. Redes Completas (Networks)
        raw_customer_net = raw_data.get("raw_customer_net", [])
        raw_vendor_net = raw_data.get("raw_vendor_net", [])
        
        networks = PrequalificationResponse.NetworksData(
            customers=self._map_nodes(
                raw_customer_net, 
                name_key="customer", 
                pending_key="emittedPaymentPending", 
                installments_key="collectedInInstallments", 
                days_key="daysSalesOutstanding"
            ),
            vendors=self._map_nodes(
                raw_vendor_net, 
                name_key="vendor", 
                pending_key="receivedPaymentPending", 
                installments_key="paidInInstallments", 
                days_key="daysPayableOutstanding"
            )
        )
        
        return {
            "concentration_last_12m": concentration,
            "networks_data": networks
        }

    def _to_concentration_item(self, item: Dict) -> PrequalificationResponse.ConcentrationItem:
        transactions = item.get("transactions", [])
        slope = 0.0
        trend_text = "Sin datos"
        
        if transactions:
            # 1. Ordenar cronológicamente
            transactions_sorted = sorted(transactions, key=lambda x: x.get("date", ""))
            
            # 2. Excluir el mes actual (regla de meses cerrados)
            current_month = datetime.now().strftime("%Y-%m")
            transactions_clean = [t for t in transactions_sorted if t.get("date") != current_month]
            
            vals = [float(t.get("total", 0.0)) for t in transactions_clean]
            
            # 3. Calcular Slope (Regresión Lineal Simple)
            n = len(vals)
            if n > 1:
                xs = range(n)
                ys = vals
                sum_x = sum(xs)
                sum_y = sum(ys)
                sum_xy = sum(x*y for x, y in zip(xs, ys))
                sum_xx = sum(x*x for x in xs)
                denominator = (n * sum_xx - sum_x * sum_x)
                
                if denominator != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / denominator
                    
                # 4. Definir Comportamiento (Usamos un umbral de $100 para no marcar "Crecimiento" por simples centavos)
                if slope > 100:
                    trend_text = "Creciendo"
                elif slope < -100:
                    trend_text = "Disminuyendo"
                else:
                    trend_text = "Constante"

        return PrequalificationResponse.ConcentrationItem(
            name=item.get("name", "N/A"),
            rfc=item.get("rfc", "N/A"),
            total_amount=item.get("total_amount", 0.0),
            percentage=item.get("percentage", 0.0),
            linear_slope=round(slope, 2),
            trend_text=trend_text
        )

    def _map_nodes(self, raw_list: Any, name_key: str, pending_key: str, installments_key: str, days_key: str) -> List[PrequalificationResponse.NetworkNode]:
        nodes = []
        if not isinstance(raw_list, list):
            return nodes
            
        def safe_float(val):
            try: return float(val)
            except: return 0.0
            
        for item in raw_list:
            nodes.append(PrequalificationResponse.NetworkNode(
                name=str(item.get(name_key, "N/A")),
                total_received=safe_float(item.get("totalReceived")),
                total_cancelled_received=safe_float(item.get("totalCancelledReceived")),
                percentage_cancelled=safe_float(item.get("percentageCancelled")),
                received_discounts=safe_float(item.get("receivedDiscounts")),
                received_credit_notes=safe_float(item.get("receivedCreditNotes")),
                payment_pending=safe_float(item.get(pending_key)),
                net_received=safe_float(item.get("netReceived")),
                pue_received=safe_float(item.get("pueReceived")),
                ppd_received=safe_float(item.get("ppdReceived")),
                ppd_count=int(item.get("ppdCount", 0)),
                payment_amount=safe_float(item.get("paymentAmount")),
                in_installments=safe_float(item.get(installments_key)),
                days_outstanding=safe_float(item.get(days_key))
            ))
        return nodes