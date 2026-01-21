from ..core.config import settings
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

class SyntageClient:
    """
    Cliente HTTP encargado EXCLUSIVAMENTE de la comunicación con la API de Syntage.
    No realiza cálculos financieros, ni decide ventanas de tiempo, ni formatea respuestas finales.
    """
    def __init__(self, api_key: str):
        self.headers = {
            "X-API-Key": api_key, 
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.base_url = settings.SYNTAGE_API_URL

    # --- 1. BUSINESS NAME & RISKS ---
    async def get_taxpayer_info(self, client: httpx.AsyncClient, rfc: str) -> Tuple[str, List[str]]:
        """
        Obtiene el nombre y los riesgos raw.
        """
        name = rfc 
        risks = []
        found_name = None

        # A. Intentar obtener nombre de facturas
        for inv_type in ["issued", "received"]:
            if found_name: break
            try:
                # Ampliamos la búsqueda de fechas por si no ha facturado reciente
                params = {"itemsPerPage": 1, "type": inv_type}
                resp = await client.get(f"{self.base_url}/taxpayers/{rfc}/invoices", params=params, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    members = data if isinstance(data, list) else data.get("hydra:member", [])
                    # --- LOG DE DEBUG ---
                    if members:
                        logger.info(f"DEBUG NAME ({inv_type}): Primer item encontrado: {str(members[0])[:200]}...")
                    else:
                        logger.info(f"DEBUG NAME ({inv_type}): Lista vacía.")
                    # --------------------

                    if members and isinstance(members[0], dict):
                        entity = members[0].get("issuer" if inv_type == "issued" else "receiver", {})
                        found_name = entity.get("name") or entity.get("razonSocial")
            except Exception as e:
                logger.warning(f"Error fetching invoices for name: {e}")

        # B. Intentar obtener nombre de endpoint base
        # Si no hay facturas, preguntamos por el contribuyente directo
        if not found_name:
            try:
                resp = await client.get(f"{self.base_url}/taxpayers/{rfc}", headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    found_name = data.get("name") or data.get("razonSocial") or data.get("businessName")
            except Exception as e:
                logger.warning(f"Error fetching taxpayer info: {e}")

        if found_name: name = found_name

        # C. Obtener Riesgos
        try:
            resp_risks = await client.get(f"{self.base_url}/insights/{rfc}/risks", headers=self.headers)
            if resp_risks.status_code == 200:
                data = resp_risks.json()
                
                # 1. Si es lista simple: ["Risk1", "Risk2"]
                if isinstance(data, list):
                    risks = [str(x) for x in data]
                
                # 2. Si es diccionario: {"taxCompliance": {"risky": false}}
                elif isinstance(data, dict):
                    # Si es formato hydra con "data": [...]
                    if "data" in data and isinstance(data["data"], list):
                        risks = [str(x) for x in data["data"]]
                    else:
                        # Formato Objeto de Riesgos
                        for key, val in data.items():
                            # Solo agregamos si 'risky' es True o si el valor es True
                            if isinstance(val, dict) and val.get("risky") is True:
                                risks.append(key)
                            elif isinstance(val, bool) and val is True:
                                risks.append(key)
                            # Si no tiene flag 'risky' pero existe, lo agregamos por precaución 
                            # (excepto si explícitamente es false)
                            elif val and not (isinstance(val, dict) and val.get("risky") is False):
                                risks.append(key)
                        
        except Exception as e:
            logger.warning(f"Error fetching risks: {e}")
            risks = [] # Fallback seguro
        
        return name, risks

    # --- 2. RAW MONTHLY DATA ---
    async def get_raw_monthly_data(self, client: httpx.AsyncClient, rfc: str, endpoint: str) -> Dict[str, Any]:
        """
        Obtiene los datos mensuales sin filtrar últimos 12 meses.
        Devuelve el diccionario completo { '2024-01': ... }
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=400) 
        params = {
            "options[periodicity]": "monthly",
            "options[type]": "total",
            "options[from]": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "options[to]": end_date.strftime("%Y-%m-%dT00:00:00.000Z")
        }

        result_map = {}
        try:
            resp = await client.get(f"{self.base_url}/insights/{rfc}/{endpoint}", params=params, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
                
                for item in items:
                    date_str = item.get("date")
                    # Normalizamos la fecha AQUÍ porque es específico de Syntage
                    norm_date = self.normalize_syntage_date(date_str)
                    if not norm_date: continue

                    val = float(item.get("mxnAmount") or item.get("amount") or 0.0)
                    type_str = item.get("type", "total")
                    
                    if endpoint == "cash-flow":
                        if norm_date not in result_map: result_map[norm_date] = {"in": 0.0, "out": 0.0}
                        if type_str == "inflow": result_map[norm_date]["in"] += val
                        elif type_str == "outflow": result_map[norm_date]["out"] += val
                    else:
                        result_map[norm_date] = val
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            
        return result_map

    # --- 3. CONCENTRACIÓN ---
    async def get_concentration_data(self, client: httpx.AsyncClient, rfc: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Devuelve listas de diccionarios planos, NO objetos Pydantic.
        El Service se encargará de convertirlos a PrequalificationResponse.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        params = {
            "options[from]": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "options[to]": end_date.strftime("%Y-%m-%dT00:00:00.000Z")
        }

        async def fetch_conc(url_suffix):
            items_out = []
            try:
                resp = await client.get(f"{self.base_url}/insights/{rfc}/{url_suffix}", params=params, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
                    
                    for i in raw_items[:5]:
                        # Devolvemos Dict puro
                        items_out.append({
                            "name": i.get("name", "N/A"),
                            "rfc": i.get("rfc", "N/A"),
                            "total_amount": float(i.get("total", 0)),
                            "percentage": float(i.get("share", 0))
                        })
            except Exception as e:
                logger.error(f"Error concentration {url_suffix}: {e}")
            return items_out

        clients = await fetch_conc("customer-concentration")
        suppliers = await fetch_conc("supplier-concentration")
        return clients, suppliers

    # --- 4. FINANCIAL STATEMENTS ---
    async def get_financial_statements_tree(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Devuelve el árbol crudo (JSON).
        """
        fs_headers = {**self.headers, "X-Insight-Format": "2022"}
        data = {"balance_sheet": {}, "income_statement": {}}
        try:
            r1 = await client.get(f"{self.base_url}/taxpayers/{rfc}/insights/metrics/balance-sheet", headers=fs_headers)
            if r1.status_code == 200: data["balance_sheet"] = r1.json()
            
            r2 = await client.get(f"{self.base_url}/taxpayers/{rfc}/insights/metrics/income-statement", headers=fs_headers)
            if r2.status_code == 200: data["income_statement"] = r2.json()
        except Exception as e:
            logger.error(f"Error fetching financial statements: {e}")
        return data
    
    # --- 5. CREDENCIALES (CIEC / BURÓ) ---
    async def get_credentials_status(self, client: httpx.AsyncClient, rfc: str) -> Tuple[str, str, str]:
        """
        Consulta CIEC y Buró.
        """
        ciec_stat = "unknown"
        buro_stat = "unknown" # unknown, found, not_found
        buro_score = "unknown"  # Score numérico si está disponible
        
        
        # --- A. VERIFICACIÓN CIEC (Endpoint Correcto: /credentials) ---
        try:
            # Documentación dice: filtrar por type='ciec' y rfc={rfc}
            params_ciec = {"type": "ciec", "rfc": rfc, "itemsPerPage": 1, "order[createdAt]": "desc"}
            resp = await client.get(f"{self.base_url}/credentials", params=params_ciec, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                # Syntage usa hydra:member para listas
                items = data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
                
                if items:
                    # Tomamos el status directo: pending, valid, invalid, error
                    ciec_stat = items[0].get("status", "unknown")
                else:
                    ciec_stat = "not_found"
            else:
                logger.warning(f"CIEC Check failed with status {resp.status_code}")

        except Exception as e:
            logger.error(f"Error fetching CIEC credential: {e}")

        # --- B. VERIFICACIÓN BURÓ (Requiere Entity ID primero) ---
        try:
            # 1. Get Entity ID
            entity_id = await self._get_entity_id(client, rfc)
            
            if not entity_id:
                logger.warning(f"DEBUG BURO: No se encontró entityId para el RFC {rfc}. No se puede consultar Buró.")
                return ciec_stat, "entity_not_found", "unknown"

            # 2. Get Report
            params_buro = {
                "itemsPerPage": 1,
                "order[createdAt]": "desc"
            }
            # URL según documentación
            url_buro = f"{self.base_url}/entities/{entity_id}/datasources/mx/buro-de-credito/reports"
            
            logger.info(f"DEBUG BURO URL: {url_buro}") # Confirmamos que la URL lleva el UUID
            
            resp_buro = await client.get(url_buro, params=params_buro, headers=self.headers)
            
            if resp_buro.status_code == 200:
                data_buro = resp_buro.json()
                items_buro = data_buro if isinstance(data_buro, list) else data_buro.get("hydra:member", []) or data_buro.get("data", [])

                if items_buro:
                    buro_stat = "active"
                    first_item = items_buro[0]
                    
                    # Lógica de extracción de Score (Corregida)
                    score_val = first_item.get("score")
                    
                    # Si no está en la raíz, buscamos en el objeto anidado
                    if not score_val and "scoreBuroCredito" in first_item:
                        sb = first_item["scoreBuroCredito"]
                        if isinstance(sb, list) and sb:
                            score_val = sb[0].get("valorScore")
                    
                    buro_score = str(score_val) if score_val else "not_found_in_json"
                else:
                    buro_stat = "not_found"
                    buro_score = "empty_list"

            elif resp_buro.status_code == 404:
                buro_stat = "not_found"
                logger.info("DEBUG BURO: Endpoint retornó 404 (Entidad sin reportes vinculados)")
            else:
                logger.warning(f"DEBUG BURO: Error {resp_buro.status_code} - {resp_buro.text}")
                
        except Exception as e:
            logger.error(f"Error fetching Buro report status: {e}")
            
        return ciec_stat, buro_stat, buro_score
    
    async def _get_entity_id(self, client: httpx.AsyncClient, rfc: str) -> Optional[str]:
        """Helper privado para obtener ID de entidad"""
        try:
            resp = await client.get(f"{self.base_url}/taxpayers/{rfc}", headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                raw = data.get("entity")
                if isinstance(raw, str) and "/entities/" in raw:
                    return raw.split("/")[-1]
                elif isinstance(raw, dict):
                    return raw.get("id")
        except Exception as e: 
            logger.error(f"Error fetching entity ID: {e}")
        return None

    # --- HELPERS DE PARSING ---
    @staticmethod
    def normalize_syntage_date(date_str: str) -> str:
        """
        Convierte fechas de Syntage '2025/Sep' o '2025-09' a formato estándar 'YYYY-MM'.
        """
        if not date_str: return ""
        
        # Mapa de meses en inglés (Syntage suele usarlos)
        month_map = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
            "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
            # Por si acaso vienen en español
            "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05", "Jun": "06",
            "Jul": "07", "Ago": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dic": "12"
        }

        # Reemplazar separador
        clean_date = date_str.replace("/", "-")
        
        try:
            parts = clean_date.split("-")
            if len(parts) == 2:
                year, month = parts
                # Si el mes es texto (Sep), lo convertimos
                if month in month_map:
                    return f"{year}-{month_map[month]}"
                # Si ya es número, aseguramos 2 dígitos
                if month.isdigit():
                    return f"{year}-{int(month):02d}"
        except:
            pass
            
        return clean_date # Retorno original si falla
    
    @staticmethod
    def parse_values_from_tree(tree: Any, target_keys: List[str]) -> Dict[str, float]:
        """
        Recorre el árbol JSON de Syntage para encontrar valores por año.
        Renombrado de 'find_values_by_year_in_tree' para indicar que es un parser.
        """
        # Normalizamos targets
        targets = [t.lower().strip() for t in target_keys]
        results = {}

        # --- CASO 1: Estructura contenedora "data" ---
        if isinstance(tree, dict) and "data" in tree and isinstance(tree["data"], list):
            return SyntageClient.parse_values_from_tree(tree["data"], target_keys)

        # --- CASO 2: Lista de nodos ---
        elif isinstance(tree, list):
            for item in tree:
                # Recursión en cada elemento
                res = SyntageClient.parse_values_from_tree(item, target_keys)
                if res:
                    for year, value in res.items():
                        # Lógica de "Merge": Si ya tenemos un valor, solo lo sobreescribimos si es diferente de 0
                        # o si el nuevo valor parece más relevante.
                        if year not in results or (results[year] == 0 and value != 0):
                            results[year] = value
            return results

        # --- CASO 3: Nodo individual (Dict) ---
        elif isinstance(tree, dict):
            category_raw = str(tree.get("category", ""))
            category = category_raw.lower().strip()
            
            is_match = False
            if category in targets: is_match = True
            else:
                # Búsqueda parcial defensiva:
                # Solo aceptamos parcial si NO es una frase compuesta peligrosa
                # (Ej: Evitar que "Impuestos" haga match con "Utilidad antes de impuestos")
                for t in targets:
                    if t in category and len(category) < len(t) * 2.5:
                        is_match = True
                        break

            # Extracción de valores si hay match
            local_results = {}
            if is_match:
                # Extraer años (claves numéricas de 4 dígitos)
                years = [k for k in tree.keys() if k.isdigit() and len(k) == 4]
                for year in years:
                    val_node = tree.get(year)
                    val = 0.0
                    if isinstance(val_node, dict):
                        raw_val = val_node.get("Total") or val_node.get("total")
                        if raw_val is not None:
                            val = float(raw_val)
                    elif isinstance(val_node, (int, float)):
                        val = float(val_node)
                    
                    local_results[year] = val

            # --- BÚSQUEDA EN HIJOS ---
            # Aunque hayamos encontrado algo aquí, los hijos pueden tener datos más específicos
            # (Ej: "Impuestos" padre puede ser 0, pero tener un hijo "ISR" con valor).
            children = tree.get("children", [])
            children_results = SyntageClient.parse_values_from_tree(children, target_keys)
            
            # --- FUSIÓN DE RESULTADOS ---
            # Si encontramos resultados en los hijos, esos suelen ser más precisos (desglose)
            if children_results:
                for year, val in children_results.items():
                    if val != 0: # Priorizamos valores no cero de los hijos
                        local_results[year] = val
            
            # Si este nodo era match exacto y tiene valores, tiene alta prioridad
            if is_match and local_results:
                # Merge con lo que traigamos de hijos
                for year, val in local_results.items():
                    if year not in results:
                        results[year] = val
                    elif val != 0: # Si tenemos valor local, lo usamos
                        results[year] = val

            # Si no hubo match local, devolvemos lo de los hijos
            if not is_match and children_results:
                return children_results

            return results if results else {}

        return {}