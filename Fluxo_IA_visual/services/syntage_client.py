from ..core.config import settings
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
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
    async def get_taxpayer_info(self, client: httpx.AsyncClient, rfc: str) -> Tuple[str, List[Dict]]:
        """
        Obtiene el nombre y la lista de riesgos.
        FIX: Agregamos filtro 'options[from]' para que los riesgos se calculen 
        sobre los últimos 12 meses, alineándose con lo que muestra el Frontend.
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
        # C. Obtener Riesgos
        try:
            # LÓGICA DE FECHAS: 12 meses pasados + Mes actual (Incompleto)
            # Ejemplo: Si hoy es 5 de Feb 2026.
            # Start: 1 de Feb 2025.
            # End: 5 de Feb 2026 (Ahora).
            
            now = datetime.now()
            
            # 1. Calculamos el "suelo" (Inicio de la ventana):
            # Tomamos el día 1 del mes actual y restamos 1 año.
            first_day_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            try:
                start_date = first_day_current_month.replace(year=first_day_current_month.year - 1)
            except ValueError:
                # Manejo de bisiestos (ej. si hoy fuera 29 feb)
                start_date = first_day_current_month.replace(year=first_day_current_month.year - 1, day=28)

            params = {
                "options[from]": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
                # FIX: Ahora el 'to' es AHORA MISMO, para incluir lo que llevamos del mes actual.
                "options[to]": now.strftime("%Y-%m-%dT00:00:00.000Z")
            }
            
            # Log para verificar la nueva ventana ampliada
            logger.info(f"Consultando Riesgos con ventana (12m + Current): {params['options[from]']} a {params['options[to]']}")

            resp_risks = await client.get(f"{self.base_url}/insights/{rfc}/risks", params=params, headers=self.headers)
            
            if resp_risks.status_code == 200:
                json_body = resp_risks.json()
                
                # Extracción robusta (Mantenemos la lógica de extracción que ya funcionó)
                if isinstance(json_body, dict):
                    if "data" in json_body and isinstance(json_body["data"], dict):
                        risks = [json_body["data"]]
                    elif "hydra:member" in json_body:
                        risks = json_body["hydra:member"]
                    elif isinstance(json_body, list):
                        risks = json_body
                
                logger.info(f"Riesgos obtenidos correctamente.")
            else:
                logger.warning(f"Error HTTP al obtener riesgos: {resp_risks.status_code}")

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

    async def get_buro_report_status(self, client: httpx.AsyncClient, entity_id: str, rfc: str) -> Dict[str, Any]:
        """
        Verifica reporte de Buró y extrae datos soportando estructuras de 
        Persona Física (cuentas) y Persona Moral (creditoFinanciero).
        """
        # Estructura base de retorno
        result = {
            "has_report": False, 
            "status": "unknown", 
            "score": None, 
            "date": None,
            "credit_lines": [],
            "inquiries": []
        }
        
        if not entity_id:
            entity_id = await self._get_entity_id(client, rfc)
            if not entity_id:
                logger.warning(f"Buró check: No Entity ID found for RFC {rfc}")
                result["status"] = "entity_not_found"
                return result

        try:
            url = f"{self.base_url}/entities/{entity_id}/datasources/mx/buro-de-credito/reports"
            # Pedimos itemsPerPage=1 porque solo nos interesa el reporte MÁS RECIENTE completo
            params = {"itemsPerPage": 1} 
            
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # DEBUG LOG
                logger.info(f"DEBUG Buró Reports RAW: {str(data)}")

                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    # Ordenar por fecha reciente
                    items.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
                    last_report = items[0]
                    data_node = last_report.get("data", {})
                    
                    result["has_report"] = True
                    result["status"] = "found"
                    
                    # Score (Manejo de lista vs valor directo)
                    score_node = data_node.get("score")
                    if isinstance(score_node, list) and score_node:
                        result["score"] = str(score_node[0].get("valorScore", "N/A"))
                    else:
                        result["score"] = str(data_node.get("score", "N/A"))
                        
                    result["date"] = last_report.get("createdAt")

                    # --- EXTRACCIÓN HÍBRIDA (PERSONA vs EMPRESA) ---
                    try:
                        # 1. Identificar Listas de Créditos
                        # Persona Física: data -> respuesta -> persona -> cuentas
                        # Empresa: data -> creditoFinanciero
                        raw_cuentas = []
                        persona_node = data_node.get("respuesta", {}).get("persona", {})
                        
                        if "creditoFinanciero" in data_node:
                            raw_cuentas = data_node["creditoFinanciero"] # Estructura Empresa
                        elif "cuentas" in persona_node:
                            raw_cuentas = persona_node["cuentas"] # Estructura Persona

                        # 2. Identificar Consultas
                        raw_consultas = []
                        if "historialConsultas" in data_node:
                            raw_consultas = data_node["historialConsultas"] # Empresa
                        elif "consultaEfectuadas" in persona_node:
                            raw_consultas = persona_node["consultaEfectuadas"] # Persona
                        
                        # Fix: A veces historialConsultas es un dict único en vez de lista
                        if isinstance(raw_consultas, dict):
                            raw_consultas = [raw_consultas]

                        # --- PROCESAMIENTO UNIFICADO ---
                        
                        # A. LÍNEAS DE CRÉDITO
                        for c in raw_cuentas:
                            # Mapeo de campos (Prioridad Persona -> Prioridad Empresa)
                            
                            # Institución
                            inst = c.get("nombreOtorgante") or c.get("tipoUsuario") or "N/A"
                            
                            # Tipo Contrato
                            tipo = c.get("tipoContrato") or c.get("tipoCredito") or "N/A"
                            
                            # Límite (Puede ser limiteCredito, creditoMaximo, o creditoMaximoUtilizado)
                            limite = (c.get("limiteCredito") or 
                                      c.get("creditoMaximo") or 
                                      c.get("creditoMaximoUtilizado"))
                            
                            # Fechas
                            apertura = c.get("fechaAperturaCuenta") or c.get("apertura")
                            ultimo_pago = c.get("fechaUltimoPago") # Suele llamarse igual
                            
                            # Saldo Vencido (Empresas lo tienen desglosado, calculamos suma si no existe total)
                            saldo_vencido = c.get("saldoVencido")
                            if saldo_vencido is None:
                                # Sumar buckets de empresa (1-29, 30-59, etc.)
                                s1 = self._parse_buro_amount(c.get("saldoVencidoDe1a29Dias"))
                                s2 = self._parse_buro_amount(c.get("saldoVencidoDe30a59Dias"))
                                s3 = self._parse_buro_amount(c.get("saldoVencidoDe60a89Dias"))
                                s4 = self._parse_buro_amount(c.get("saldoVencidoDe90a119Dias"))
                                s5 = self._parse_buro_amount(c.get("saldoVencidoDe120a179Dias"))
                                s6 = self._parse_buro_amount(c.get("saldoVencidoDe180DiasOMas"))
                                saldo_vencido = s1 + s2 + s3 + s4 + s5 + s6

                            result["credit_lines"].append({
                                "institution": inst,
                                "account_type": str(tipo),
                                "credit_limit": self._parse_buro_amount(limite),
                                "current_balance": self._parse_buro_amount(c.get("saldoActual") or c.get("saldoVigente")),
                                "past_due_balance": self._parse_buro_amount(saldo_vencido),
                                "payment_frequency": c.get("frecuenciaPagos", "N/A"),
                                "opening_date": self._parse_buro_date(apertura),
                                "last_payment_date": self._parse_buro_date(ultimo_pago),
                                "payment_history": c.get("historicoPagos", "")
                            })

                        # B. CONSULTAS
                        for cons in raw_consultas:
                            # Institución
                            inst_cons = cons.get("nombreOtorgante") or cons.get("tipoUsuario") or "N/A"
                            
                            result["inquiries"].append({
                                "institution": inst_cons,
                                "inquiry_date": self._parse_buro_date(cons.get("fechaConsulta")),
                                "contract_type": cons.get("tipoContrato", "N/A"),
                                "amount": self._parse_buro_amount(cons.get("importeContrato"))
                            })
                                
                    except Exception as e:
                        logger.error(f"Error parseando detalle profundo de Buró: {e}")

                else:
                    result["status"] = "not_found"
                    
            elif resp.status_code == 404:
                result["status"] = "not_found"
                
        except Exception as e:
            logger.error(f"Error general Buró: {e}")
            
        return result

    async def get_compliance_opinion(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Obtiene la Opinión de Cumplimiento (32-D) más reciente.
        FIX: Usa el endpoint específico /tax-compliance-checks para obtener 
        estatus real y fecha dinámica ('checkedAt'), eliminando fechas hardcodeadas.
        """
        result = {"status": "unknown", "date": None}
        
        try:
            # Ordenamos por fecha descendente para obtener la última ejecución real
            params = {
                "order[checkedAt]": "desc",
                "itemsPerPage": 1
            }
            
            url = f"{self.base_url}/taxpayers/{rfc}/tax-compliance-checks"
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                # Manejo robusto de Hydra (Lista vs Diccionario)
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    latest_check = items[0]
                    
                    # 1. Estatus
                    # La API devuelve: "positive", "negative", "no_obligations", "activity_suspended"
                    # Lo pasamos directo o lo normalizamos según tu lógica de negocio.
                    raw_result = latest_check.get("result")
                    result["status"] = raw_result if raw_result else "unknown"
                    
                    # 2. Fecha Real
                    # "checkedAt" es la fecha exacta cuando Syntage verificó esto con el SAT.
                    result["date"] = latest_check.get("checkedAt")
                    
                    logger.info(f"Compliance Opinion actualizada: {result['status']} fecha {result['date']}")
                else:
                    result["status"] = "not_found"
                    logger.info(f"No se encontraron registros de compliance checks para {rfc}")

            elif resp.status_code == 404:
                result["status"] = "not_found"
                
        except Exception as e:
            logger.error(f"Error fetching Compliance Opinion: {e}")
            
        return result
    
    async def _get_entity_id(self, client: httpx.AsyncClient, rfc: str) -> Optional[str]:
        """
        Busca el UUID de la Entidad usando el filtro específico taxpayer.id.
        Fuente: Documentación de Syntage (GET /entities?taxpayer.id={RFC})
        """
        try:
            # Usamos el filtro 'taxpayer.id' que apunta específicamente al RFC dentro del objeto taxpayer
            params = {
                "taxpayer.id": rfc, 
                "itemsPerPage": 1  # Debería ser único si el RFC es exacto
            }
            
            resp = await client.get(f"{self.base_url}/entities", params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
                
                if items:
                    # El endpoint /entities devuelve objetos Entidad.
                    # El 'id' de nivel superior es el UUID que necesitamos para Buró.
                    entity = items[0]
                    found_id = entity.get("id")
                    
                    logger.info(f"Entity ID resuelto exitosamente para {rfc}: {found_id}")
                    return found_id
                else:
                    logger.warning(f"Entity Search: No se encontró entidad para taxpayer.id={rfc}")

        except Exception as e:
            logger.error(f"Error crítico resolviendo Entity ID: {e}")
            
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
    
    async def get_tax_status(self, client: httpx.AsyncClient, rfc: str) -> List[Dict]:
        """
        Obtiene las actividades económicas desde /taxpayers/{id}/tax-status
        """
        activities = []
        try:
            # Primero intentamos obtener el ID del taxpayer si no lo tenemos, 
            # pero asumimos que el RFC funciona en la ruta para taxpayer endpoints 
            # o usamos la búsqueda de entity previa para obtener el ID real.
            # Syntage permite usar RFC en rutas de taxpayers usualmente.
            
            resp = await client.get(f"{self.base_url}/taxpayers/{rfc}/tax-status", headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                # Buscamos el objeto más reciente o iteramos
                # El endpoint suele devolver una lista de status.
                if items:
                    # Tomamos el status actual (usualmente el primero o el activo)
                    current_status = items[0] 
                    raw_acts = current_status.get("economicActivities", [])
                    
                    for act in raw_acts:
                        activities.append({
                            "name": act.get("name"),
                            "percentage": float(act.get("percentage") or 0),
                            "start_date": act.get("startDate")
                        })
        except Exception as e:
            logger.warning(f"Error fetching tax status: {e}")
        
        return activities
    
    async def get_entity_detail(self, client: httpx.AsyncClient, rfc: str) -> Dict[str, Any]:
        """
        Busca la entidad y retorna ID y Fecha de Registro SAT.
        Reemplaza o complementa a _get_entity_id para traer más datos.
        """
        result = {"id": None, "registration_date": None}
        try:
            params = {"taxpayer.id": rfc, "itemsPerPage": 1}
            resp = await client.get(f"{self.base_url}/entities", params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    entity = items[0]
                    result["id"] = entity.get("id")
                    # Extraer fecha de registro del taxpayer anidado
                    taxpayer = entity.get("taxpayer", {})
                    result["registration_date"] = taxpayer.get("registrationDate")
                    
                    logger.info(f"Entidad encontrada. ID: {result['id']}, RegDate: {result['registration_date']}")
        except Exception as e:
            logger.error(f"Error getting entity detail: {e}")
        
        return result
    
    @staticmethod
    def _parse_buro_amount(val_str: Any) -> float:
        """Limpia montos de buró (ej: '0001200+' -> 1200.0)"""
        if not val_str: return 0.0
        try:
            # Eliminar símbolos no numéricos comunes en Buró (+, -)
            clean = str(val_str).replace("+", "").replace("-", "").strip()
            return float(clean)
        except:
            return 0.0

    @staticmethod
    def _parse_buro_date(date_str: str) -> str:
        """Convierte DDMMYYYY a YYYY-MM-DD"""
        if not date_str or len(str(date_str)) != 8:
            return str(date_str)
        try:
            d = str(date_str)
            # Formato Buró: 31122023 (DDMMYYYY)
            return f"{d[4:]}-{d[2:4]}-{d[:2]}" # YYYY-MM-DD
        except:
            return date_str