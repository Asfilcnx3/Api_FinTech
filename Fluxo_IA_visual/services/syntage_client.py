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
                json_body = resp_risks.json()
                # DEBUG
                logger.info(f"DEBUG RISKS: Response body: {str(json_body)}")
                # Extraemos el diccionario 'data' completo. 
                # Si no existe 'data', devolvemos el body entero por seguridad.
                risks = json_body.get("data", json_body) if isinstance(json_body, dict) else {}
                
        except Exception as e:
            logger.warning(f"Error fetching risks list: {e}")
        
        return name, risks

    # --- 2. RAW MONTHLY DATA ---
    async def get_raw_monthly_data(self, client: httpx.AsyncClient, rfc: str, endpoint: str) -> Dict[str, Any]:
        """
        Obtiene los datos mensuales sin filtrar últimos 3 años (~1100 días) para permitir que el modelo de predicción
        detecte estacionalidad (ciclos anuales).
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1100) 
        
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
    async def get_ciec_status(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Devuelve estatus y fecha de la última CIEC.
        """
        result = {"status": "unknown", "date": None}
        try:
            params = {"type": "ciec", "rfc": rfc, "itemsPerPage": 1, "order[createdAt]": "desc"}
            resp = await client.get(f"{self.base_url}/credentials", params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                # Lista vs Dict
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    item = items[0]
                    raw_status = item.get("status")
                    result["status"] = "active" if raw_status == "valid" else "inactive"
                    result["date"] = item.get("createdAt")
                else:
                    result["status"] = "not_found"
        except Exception as e:
            logger.error(f"Error CIEC: {e}")
        return result

    async def get_buro_report_status(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Verifica reporte de Buró. Maneja correctamente el 404 cuando no hay reportes.
        """
        result = {"has_report": False, "status": "unknown", "score": None, "date": None}
        
        entity_id = await self._get_entity_id(client, rfc)
        if not entity_id:
            result["status"] = "entity_not_found"
            return result

        try:
            url = f"{self.base_url}/entities/{entity_id}/datasources/mx/buro-de-credito/reports"
            params = {"itemsPerPage": 1, "order[createdAt]": "desc"}
            
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    last_report = items[0]
                    result["has_report"] = True
                    result["status"] = "found"
                    result["score"] = last_report.get("score")
                    
                    # Fecha
                    date_val = last_report.get("createdAt")
                    if not date_val:
                        try:
                            raw_d = last_report["data"]["respuesta"]["persona"]["cuentas"][0]["fechaReporte"]
                            if raw_d and len(raw_d) == 8:
                                date_val = f"{raw_d[4:]}-{raw_d[2:4]}-{raw_d[:2]}"
                        except: pass
                    result["date"] = date_val
                else:
                    result["status"] = "not_found"
            elif resp.status_code == 404:
                result["status"] = "not_found"
                result["has_report"] = False
                
        except Exception as e:
            logger.error(f"Error Buró: {e}")
            
        return result

    async def get_compliance_opinion(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Obtiene la Opinión de Cumplimiento. Busca fecha en niveles superiores si no está en el objeto.
        """
        result = {"status": "unknown", "date": None}
        try:
            resp = await client.get(f"{self.base_url}/insights/{rfc}/risks", headers=self.headers)
            
            if resp.status_code == 200:
                json_body = resp.json()
                
                # Acceso seguro a data -> taxCompliance
                data_node = json_body.get("data", json_body) if isinstance(json_body, dict) else {}
                compliance = data_node.get("taxCompliance", {})
                
                if isinstance(compliance, dict) and compliance:
                    is_risky = compliance.get("risky")
                    if is_risky is False: result["status"] = "positive"
                    elif is_risky is True: result["status"] = "negative"
                    
                    # Fecha (usualmente no viene aquí, pero por si acaso)
                    result["date"] = compliance.get("updatedAt") or compliance.get("date")
                else:
                    result["status"] = "not_found"
        except Exception as e:
            logger.error(f"Error Compliance: {e}")
            
        return result
    
    async def _get_entity_id(self, client: httpx.AsyncClient, rfc: str) -> Optional[str]:
        """
        Busca el UUID de la Entidad asociado al RFC.
        Maneja respuestas tipo lista directa o colección Hydra.
        """
        # 1. INTENTO PRINCIPAL: Buscar en la colección de Entidades
        try:
            params = {"rfc": rfc, "itemsPerPage": 1}
            resp = await client.get(f"{self.base_url}/entities", params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Parseo robusto Lista vs Dict
                items = []
                if isinstance(data, list): items = data
                elif isinstance(data, dict): items = data.get("hydra:member", []) or data.get("data", [])
                
                if items and isinstance(items[0], dict):
                    return items[0].get("id")
                    
        except Exception as e:
            logger.error(f"Error searching entity: {e}")
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