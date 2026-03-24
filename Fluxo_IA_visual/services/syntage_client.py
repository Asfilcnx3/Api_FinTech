from ..core.config import settings
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import httpx
import logging

logger = logging.getLogger(__name__)

# Mapeo de códigos de Tipo de Crédito / Contrato a Descripción
CATALOGO_TIPOS_CREDITO = {
    "3231": "Cartera de Arrendamiento Financiero Vigente",
    "1314": "No Disponible",
    "1323": "Créditos Reestructurados",
    "6291": "Fianzas",
    "1310": "Préstamos para la vivienda",
    "1327": "Arrendamiento Financiero Sindicado",
    "1300": "Cartera de arrendamiento Puro y créditos",
    "1308": "Créditos Refaccionarios",
    "6103": "Adeudos por Aval",
    "3012": "Cartera de Factoraje sin Recursos",
    "1306": "Préstamos con garantía de unidades industriales",
    "3230": "Anticipo a Clientes Por Promesa de Factoraje",
    "1317": "Créditos venidos a menos aseg. Gtias. Adicionales",
    "3011": "Cartera de Factoraje con Recursos",
    "6280": "Línea de Crédito",
    "1316": "Otros adeudos vencidos",
    "1320": "Cartera de Arrendamiento Financiero Vigente",
    "1321": "Cartera de Arrendamiento Financiero Sindicado con Aportación",
    "1324": "Créditos Renovados",
    "1322": "Crédito de Arrendamiento",
    "1311": "Otros créditos con garantía inmobiliaria",
    "1340": "Cartera descontada con Inst. de Crédito",
    "6270": "Crédito Automotriz",
    "1303": "Con colateral",
    "6290": "Seguros",
    "6228": "Fideicomisos Prog. apoyo crediticio planta productiva Nac.",
    "1341": "Redescuento otra cartera descontada",
    "6230": "Fideicomisos Prog. apoyo deudores vivienda UDIS",
    "1304": "Prendario",
    "1301": "Descuentos",
    "6240": "Aba Pasem II",
    "1350": "Prestamos con Fideicomisos de Garantía",
    "6250": "Tarjeta de Servicio",
    "1342": "Redescuento cartera reestructurada (Fidec.)",
    "1302": "Quirografario",
    "1307": "Créditos de habilitación o avío",
    "1380": "Tarjeta de Crédito empresarial / Corporativa",
    "6229": "Fideicomisos Prog. apoyo crediticio Estados y Municipios",
    "6105": "Cartas de Créditos No Dispuestas",
    "2303": "Cartas de Crédito",
    "1309": "Prestamos Inmobil Emp Prod de Bienes o Servicios",
    "6292": "Fondos y Fideicomisos",
    "6260": "Crédito Fiscal",
    "1305": "Créditos simples y créditos en cuenta corriente"
}

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
                    # if members:
                    #     logger.debug(f"DEBUG NAME ({inv_type}): Primer item encontrado: {str(members[0])[:200]}...")
                    # else:
                    #     logger.debug(f"DEBUG NAME ({inv_type}): Lista vacía.")
                    # # --------------------

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
            # logger.debug(f"Consultando Riesgos con ventana (12m + Current): {params['options[from]']} a {params['options[to]']}")

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
                
                logger.debug(f"Riesgos obtenidos correctamente.")
            else:
                logger.warning(f"Error HTTP al obtener riesgos: {resp_risks.status_code}")

        except Exception as e:
            logger.warning(f"Error fetching risks list: {e}")
        
        return name, risks

    # --- 2. RAW MONTHLY DATA ---
    async def get_raw_monthly_data(self, client: httpx.AsyncClient, rfc: str, endpoint: str) -> Dict[str, Any]:
        """
        Retorna mapa: date -> { "amount": float, "count": int } (para sales/exp)
        O date -> { "in": {amt, count}, "out": {amt, count} } (para cash-flow)
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
                    count = int(item.get("count") or item.get("movements") or 0) # Intentar obtener conteo
                    type_str = item.get("type", "total")
                    
                    if endpoint == "cash-flow":
                        if norm_date not in result_map: 
                            result_map[norm_date] = {
                                "in": {"amount": 0.0, "count": 0}, 
                                "out": {"amount": 0.0, "count": 0}
                            }
                        
                        if type_str == "inflow": 
                            result_map[norm_date]["in"]["amount"] += val
                            result_map[norm_date]["in"]["count"] += count
                        elif type_str == "outflow": 
                            result_map[norm_date]["out"]["amount"] += val
                            result_map[norm_date]["out"]["count"] += count
                    else:
                        # Para Sales y Expenditures
                        result_map[norm_date] = {"amount": val, "count": count}
        
        except Exception as e:
            # Usar repr(e) dirá la clase del error
            logger.error(f"Error fetching {endpoint}: {repr(e)}")
            
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
                        items_out.append({
                            "name": i.get("name", "N/A"),
                            "rfc": i.get("rfc", "N/A"),
                            "total_amount": float(i.get("total", 0)),
                            "percentage": float(i.get("share", 0)),
                            "transactions": i.get("transactions", [])
                        })
            except Exception as e:
                logger.error(f"Error concentration {url_suffix}: {e}")
            return items_out

        clients = await fetch_conc("customer-concentration")
        suppliers = await fetch_conc("supplier-concentration")
        return clients, suppliers

    async def get_network_data(self, client: httpx.AsyncClient, entity_id: str, network_type: str) -> Dict[str, Any]:
        """
        Obtiene la red de clientes o proveedores.
        network_type: 'customer-network' o 'vendor-network'
        """
        # Según la documentación: /entities/{entityId}/insights/metrics/{network_type}
        url = f"{self.base_url}/entities/{entity_id}/insights/metrics/{network_type}"
        
        try:
            # Hacemos la petición básica. Algunos endpoints de metrics requieren el header de formato, 
            # lo agregamos por si acaso, tal como en los estados financieros.
            headers = {**self.headers, "X-Insight-Format": "2022"}
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener {network_type}: {resp.text}")
                return {"error_status": resp.status_code}
                
        except Exception as e:
            logger.error(f"Error fetching {network_type}: {e}")
            return {}

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
                    # Sacamos la fecha de la última extracción real sincronizada
                    result["last_extraction_date"] = item.get("updatedAt") 
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
            "inquiries": [],
            "inquiries_summary": []
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
#                logger.info(f"DEBUG Buró Reports RAW: {str(data)}")

                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    # Ordenar por fecha reciente
                    items.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
                    last_report = items[0]
                    data_node = dict(last_report.get("data", {}))

                    # Log para verificar la estructura del bloque de datos del reporte
                    # logger.info(f"DEBUG Buró Report Data Node: {str(data_node)[:500]}...")
                    
                    result["has_report"] = True
                    result["status"] = "found"

                    result["raw_buro_data"] = data_node # Guardamos el bloque de datos crudo para volcado total
                    
                    # Log para verificar que el bloque de datos crudo se guardó correctamente
                    # logger.info(f"DEBUG Buró Raw Data Guardado: {str(result['raw_buro_data'])[:500]}...")


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
                        temp_lines = []
                        total_vigente = 0.0

                        # Contadores de cubetas de morosidad
                        sum_1_29 = sum_30_59 = sum_60_89 = sum_90_119 = sum_120_179 = sum_180_plus = 0.0
                        
                        # PASADA 1: Extraer datos crudos
                        from datetime import datetime, timedelta
                        
                        for c in raw_cuentas:

                            # LOG DEBUG que se borrará
                            # logging.info(f"DEBUG PARA CUENTAS: {raw_cuentas}")

                            inst = c.get("nombreOtorgante") or c.get("tipoUsuario") or "N/A"
                            tipo_codigo = str(c.get("tipoContrato") or c.get("tipoCredito") or "N/A")
                            tipo_desc = CATALOGO_TIPOS_CREDITO.get(tipo_codigo, tipo_codigo)
                            
                            limite = c.get("limiteCredito") or c.get("creditoMaximo") or c.get("creditoMaximoUtilizado")
                            saldo_vigente = self._parse_buro_amount(c.get("saldoActual") or c.get("saldoVigente"))
                            total_vigente += saldo_vigente
                            
                            apertura = c.get("fechaAperturaCuenta") or c.get("apertura")
                            ultimo_pago = c.get("fechaUltimoPago")
                            cierre = c.get("fechaCierreCuenta") or c.get("fechaCierre") or c.get("cierre")
                            
                            actualizacion_raw = c.get("ultimoPeriodoActualizado") or c.get("fechaReporte") or c.get("fechaActualizacion") or c.get("actualizacion")
                            actualizacion_parsed = "N/A"
                            if actualizacion_raw:
                                s_act = str(actualizacion_raw).strip()
                                if len(s_act) == 6 and s_act.isdigit():
                                    actualizacion_parsed = f"{s_act[:4]}-{s_act[4:6]}-01"
                                else:
                                    actualizacion_parsed = self._parse_buro_date(s_act)

                            # --- MODIFICACIÓN AQUÍ ---
                            v_1_29 = self._parse_buro_amount(c.get("saldoVencidoDe1a29Dias"))
                            v_30_59 = self._parse_buro_amount(c.get("saldoVencidoDe30a59Dias"))
                            v_60_89 = self._parse_buro_amount(c.get("saldoVencidoDe60a89Dias"))
                            v_90_119 = self._parse_buro_amount(c.get("saldoVencidoDe90a119Dias"))
                            v_120_179 = self._parse_buro_amount(c.get("saldoVencidoDe120a179Dias"))
                            v_180_plus = self._parse_buro_amount(c.get("saldoVencidoDe180DiasOMas"))
                            
                            # Sumamos a los totales globales
                            sum_1_29 += v_1_29
                            sum_30_59 += v_30_59
                            sum_60_89 += v_60_89
                            sum_90_119 += v_90_119
                            sum_120_179 += v_120_179
                            sum_180_plus += v_180_plus
                            
                            saldo_vencido = c.get("saldoVencido")
                            if saldo_vencido is None:
                                saldo_vencido = sum([
                                    self._parse_buro_amount(c.get(f)) for f in [
                                        "saldoVencidoDe1a29Dias", "saldoVencidoDe30a59Dias", "saldoVencidoDe60a89Dias",
                                        "saldoVencidoDe90a119Dias", "saldoVencidoDe120a179Dias", "saldoVencidoDe180DiasOMas"
                                    ]
                                ])

                            hist_pagos = str(c.get("historicoPagos") or "")
                            mop_lc = hist_pagos.count("LC")
                            temp_hist = hist_pagos.replace("LC", "")
                            
                            breakdown = {f"mop_{k}": temp_hist.count(k) for k in "123456790U-"}
                            breakdown["mop_nd"] = breakdown.pop("mop_-")
                            breakdown["mop_lc"] = mop_lc

                            # Nuevos campos crudos
                            moneda_raw = c.get("moneda", "")
                            moneda_str = "MXN" if moneda_raw == "001" else moneda_raw
                            plazo_dias = int(c.get("plazo") or 0)
                            
                            apertura_parsed = self._parse_buro_date(apertura)
                            
                            # Cálculo de Fecha Final
                            fecha_final = None
                            if apertura_parsed and plazo_dias > 0:
                                try:
                                    dt_apertura = datetime.strptime(apertura_parsed, "%Y-%m-%d")
                                    dt_final = dt_apertura + timedelta(days=plazo_dias)
                                    fecha_final = dt_final.strftime("%Y-%m-%d")
                                except:
                                    pass

                            temp_lines.append({
                                "institution": inst,
                                "account_type": tipo_desc,
                                "credit_limit": self._parse_buro_amount(limite),
                                "current_balance": saldo_vigente,
                                "past_due_balance": self._parse_buro_amount(saldo_vencido),
                                "payment_frequency": c.get("frecuenciaPagos", "N/A"),
                                "opening_date": apertura_parsed,
                                "last_payment_date": self._parse_buro_date(ultimo_pago),
                                "payment_history": hist_pagos,
                                "update_date": actualizacion_parsed,
                                "mop_breakdown": breakdown,
                                "account_number": c.get("numeroCuenta") or "",
                                "user_type": c.get("tipoUsuario") or inst,
                                "closing_date": self._parse_buro_date(cierre),
                                "term_days": plazo_dias,
                                "currency": moneda_str,
                                "exchange_rate": float(c.get("tipoCambio") or 1.0),
                                "max_delay": int(c.get("atrasoMayor") or 0),
                                "initial_balance": self._parse_buro_amount(c.get("saldoInicial")),
                                "final_date": fecha_final
                            })

                        # PASADA 2: Calcular Ponderaciones y Pagos Mensuales
                        # Obtenemos FechaConsulta (C1 en Excel) en lugar de datetime.now()
                        report_date = datetime.now() 
                        if "encabezado" in data_node and "fechaConsulta" in data_node["encabezado"]:
                            fc_raw = str(data_node["encabezado"]["fechaConsulta"]).strip()
                            try:
                                if "-" in fc_raw:
                                    report_date = datetime.strptime(fc_raw[:10], "%Y-%m-%d")
                                elif len(fc_raw) == 8 and fc_raw.isdigit():
                                    report_date = datetime.strptime(fc_raw, "%d%m%Y")
                            except: pass

                        datos_generales = data_node.get("datosGenerales", {})
                        logger.debug(f"Debug de datos generales: {datos_generales}")
                        if datos_generales:
                            def calculate_inquiry_block(keys_list):
                                v_mas24 = int(datos_generales.get(keys_list[0]) or 0)
                                v_24m = int(datos_generales.get(keys_list[1]) or 0)
                                v_12m = int(datos_generales.get(keys_list[2]) or 0)
                                v_3m = int(datos_generales.get(keys_list[3]) or 0)

                                avg_24m = v_24m / 24.0
                                avg_12m = v_12m / 12.0
                                avg_3m = v_3m / 3.0

                                growth_12_vs_24 = (avg_12m / avg_24m - 1) if avg_24m > 0 else 0.0
                                growth_3_vs_12 = (avg_3m / avg_12m - 1) if avg_12m > 0 else 0.0

                                return [
                                    {"concept": keys_list[0], "quantity": v_mas24, "equivalent_months": None, "monthly_average": None, "growth_vs_previous": None},
                                    {"concept": keys_list[1], "quantity": v_24m, "equivalent_months": 24, "monthly_average": round(avg_24m, 2), "growth_vs_previous": None},
                                    {"concept": keys_list[2], "quantity": v_12m, "equivalent_months": 12, "monthly_average": round(avg_12m, 2), "growth_vs_previous": round(growth_12_vs_24, 4)},
                                    {"concept": keys_list[3], "quantity": v_3m, "equivalent_months": 3, "monthly_average": round(avg_3m, 2), "growth_vs_previous": round(growth_3_vs_12, 4)}
                                ]

                            comercial_keys = [
                                "consultaEmpresaComercialMas24Meses", "consultaEmpresaComercialUltimos24Meses",
                                "consultaEmpresaComercialUltimos12Meses", "consultaEmpresaComercialUltimos3Meses"
                            ]
                            financiera_keys = [
                                "consultaEntidadFinancieraMas24Meses", "consultaEntidadFinancieraUltimos24Meses",
                                "consultaEntidadFinancieraUltimos12Meses", "consultaEntidadFinancieraUltimos3Meses"
                            ]

                            result["inquiries_summary"].extend(calculate_inquiry_block(comercial_keys))
                            result["inquiries_summary"].extend(calculate_inquiry_block(financiera_keys))
                            logger.debug(f"Debug_Resultados: {result["inquiries_summary"]}")

                        for line in temp_lines:
                            # log de debug
                            # logger.info(f"log de inicial balance {line["initial_balance"]}")
                            # logger.info(f"log de past due balance {line["past_due_balance"]}")

                            vigente = line["current_balance"]
                            
                            # Ponderación 1 (%) -> =+T3/$T$1
                            weight_1 = (vigente / total_vigente) if total_vigente > 0 else 0.0
                            line["weighting_pct"] = weight_1
                            
                            # Plazo Restante -> =IF(H3+N3<$C$1,0,N3-($C$1-H3))
                            restante_dias = 0
                            if line["final_date"]:
                                try:
                                    dt_final = datetime.strptime(line["final_date"], "%Y-%m-%d")
                                    if dt_final >= report_date:
                                        restante_dias = (dt_final - report_date).days
                                except: pass
                            line["remaining_term_days"] = restante_dias
                            
                            # Ponderación 2 -> =MROUND(U3*V3, 1)
                            # Equivalente matemático: redondear a 0 decimales
                            line["weighting_days"] = float(round(weight_1 * restante_dias, 0))
                            
                            # Pago Mensual -> =IF(T3>0,IF(AND(V3=0,T3>0),T3,IF(V3<30.4,T3,T3/(V3/30.4))),0)
                            if vigente > 0:
                                if restante_dias == 0 or restante_dias < 30.4:
                                    line["monthly_payment"] = vigente
                                else:
                                    line["monthly_payment"] = vigente / (restante_dias / 30.4)
                            else:
                                line["monthly_payment"] = 0.0
                                
                            result["credit_lines"].append(line)
                        
                        # --- CONSTRUCCIÓN DEL SUMMARY METRICS ---
                        # Evaluamos "None", "N/A" o vacío en lugar de un booleano simple
                        sum_saldo_inicial_activo = sum(
                            l["initial_balance"] for l in temp_lines 
                            if str(l.get("closing_date")).strip() in ["None", "N/A", ""]
                        )
                        sum_saldo_vencido_vigente = sum(
                            l["past_due_balance"] for l in temp_lines
                            if str(l.get("closing_date")).strip() in ["None", "N/A", ""]
                        )
                        sum_saldo_vencido = sum(l["past_due_balance"] for l in temp_lines)
                        sum_pond_2 = sum(l["weighting_days"] for l in temp_lines)
                        pond_2_years = round(sum_pond_2 / 360, 2) if sum_pond_2 > 0 else 0.0
                        sum_pago_mensual = sum(l["monthly_payment"] for l in temp_lines)
                        pago_anual = (total_vigente / pond_2_years) if pond_2_years > 0 else 0.0
                        pago_mensual_2 = pago_anual / 12
                        
                        # Encontrar la tendencia del 71% de la lista que ya calculamos
                        trend_pct = 0.0
                        for r in result["inquiries_summary"]:
                            if r["concept"] == "consultaEntidadFinancieraUltimos3Meses":
                                trend_pct = r["growth_vs_previous"] or 0.0
                                break
                                
                        if trend_pct > 0: trend_text = "Han ido aumentando sus consultas"
                        elif trend_pct < 0: trend_text = "Han ido disminuyendo sus consultas"
                        else: trend_text = "Estables"

                        def make_bucket(amt):
                            return {
                                "amount": amt,
                                "percentage": round(amt / total_vigente, 4) if total_vigente > 0 else 0.0
                            }

                        result["summary_metrics"] = {
                            "inquiries_trend_text": trend_text,
                            "inquiries_trend_pct": trend_pct,
                            "total_open_max_amount": sum_saldo_inicial_activo,
                            "total_current_balance": total_vigente,
                            "total_past_due": sum_saldo_vencido,
                            "total_open_past_due": sum_saldo_vencido_vigente,
                            "monthly_payment_1": sum_pago_mensual,
                            "monthly_payment_2": pago_mensual_2,
                            "weighted_term_years": pond_2_years,
                            "bucket_1_29": make_bucket(sum_1_29),
                            "bucket_30_59": make_bucket(sum_30_59),
                            "bucket_60_89": make_bucket(sum_60_89),
                            "bucket_90_119": make_bucket(sum_90_119),
                            "bucket_120_179": make_bucket(sum_120_179),
                            "bucket_180_plus": make_bucket(sum_180_plus)
                        }

                        # logger.info(f"summary metrics raw: {result["summary_metrics"]}")

                        # B. CONSULTAS
                        for cons in raw_consultas:
                            # Institución
                            inst_cons = cons.get("nombreOtorgante") or cons.get("tipoUsuario") or "N/A"
                            
                            # --- LÓGICA DE MAPEO PARA CONSULTAS ---
                            tipo_cons_codigo = str(cons.get("tipoContrato", "N/A"))
                            tipo_cons_desc = CATALOGO_TIPOS_CREDITO.get(tipo_cons_codigo, tipo_cons_codigo)
                            
                            result["inquiries"].append({
                                "institution": inst_cons,
                                "inquiry_date": self._parse_buro_date(cons.get("fechaConsulta")),
                                "contract_type": tipo_cons_desc,
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
        Obtiene la Opinión de Cumplimiento (32-D) más reciente y el ID de su archivo.
        """
        result = {"status": "unknown", "date": None, "file_id": None} # <--- Agregamos file_id
        
        try:
            params = {
                "order[checkedAt]": "desc",
                "itemsPerPage": 1
            }
            
            url = f"{self.base_url}/taxpayers/{rfc}/tax-compliance-checks"
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                if items:
                    latest_check = items[0]
                    raw_result = latest_check.get("result")
                    result["status"] = raw_result if raw_result else "unknown"
                    result["date"] = latest_check.get("checkedAt")
                    
                    # Extraer el ID del archivo PDF asociado
                    file_node = latest_check.get("file", {})
                    # A veces viene como string "/files/uuid" o como objeto con "id"
                    if isinstance(file_node, dict):
                        result["file_id"] = file_node.get("id")
                    elif isinstance(file_node, str):
                        result["file_id"] = file_node.split("/")[-1]
                        
                else:
                    result["status"] = "not_found"
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
                    
                    logger.debug(f"Entity ID resuelto exitosamente para {rfc}: {found_id}")
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
                    
                    logger.debug(f"Entidad encontrada. ID: {result['id']}, RegDate: {result['registration_date']}")
        except Exception as e:
            logger.error(f"Error getting entity detail: {e}")
        
        return result

    async def get_products_and_services(self, client: httpx.AsyncClient, entity_id: str, type_ps: str) -> List[Dict]:
        """
        type_ps: 'sold' o 'bought'
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365) # Últimos 12 meses
        
        # Quitamos el order[total] temporalmente por si eso estaba rompiendo el endpoint
        params = {
            "options[from]": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "options[to]": end_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "itemsPerPage": 50
        }
        
        url = f"{self.base_url}/entities/{entity_id}/insights/products-and-services-{type_ps}"
        
        try:
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Extracción robusta multicapa
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    # Intentamos con las 3 formas comunes de Syntage
                    items = data.get("hydra:member") or data.get("data") or data.get("respuesta") or []
                
                # Si sigue vacío pero la respuesta fue 200, imprimimos qué nos mandaron para debuggear
                if not items:
                    logger.warning(f"Productos {type_ps} regresó 200 OK pero vacío. RAW: {str(data)[:200]}")
                    
                return items
            else:
                # Si falló la petición, imprimimos el error exacto de Syntage
                logger.warning(f"Error HTTP {resp.status_code} en productos {type_ps}: {resp.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching products {type_ps}: {e}")
            return []
    
    async def get_employees_insight(self, client: httpx.AsyncClient, entity_id: str) -> List[Dict]:
        """
        Obtiene el número de empleados agrupado mensualmente (últimos 24 meses).
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730) # 730 días (24 meses)

        params = {
            "options[from]": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "options[to]": end_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "options[periodicity]": "monthly"
        }
        
        try:
            url = f"{self.base_url}/entities/{entity_id}/insights/employees"
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                raw_list = data.get("data", [])
                
                # --- LOG DE DEBUG 1: ORIGEN ---
                # logger.info(f"DEBUG EMPLEADOS (API): {entity_id} trajo {len(raw_list)} registros. RAW: {str(raw_list)[:300]}")
                
                return raw_list
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener empleados.")
        except Exception as e:
            logger.error(f"Error fetching employees insight: {e}")
            
        return []
    
    async def get_invoicing_blacklist(self, client: httpx.AsyncClient, entity_id: str) -> List[Dict]:
        """
        Obtiene el resumen de contrapartes en lista negra (69-B del SAT).
        """
        try:
            url = f"{self.base_url}/entities/{entity_id}/insights/invoicing-blacklist"
            resp = await client.get(url, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                # Syntage puede devolverlo directo, en 'data', o en 'hydra:member'
                return data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener lista negra.")
        except Exception as e:
            logger.error(f"Error fetching invoicing blacklist: {e}")
            
        return []

    async def get_rpc_records(self, client: httpx.AsyncClient, entity_id: str) -> List[Dict]:
        """
        Obtiene el listado de entidades en el RPC para este contribuyente.
        """
        try:
            url = f"{self.base_url}/entities/{entity_id}/datasources/rpc/entidades"
            resp = await client.get(url, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener RPC.")
        except Exception as e:
            logger.error(f"Error fetching RPC records: {e}")
        return []

    async def get_rug_records(self, client: httpx.AsyncClient, entity_id: str) -> List[Dict]:
        """
        Obtiene el listado de operaciones/garantías en el RUG.
        """
        try:
            url = f"{self.base_url}/entities/{entity_id}/datasources/rug/operaciones"
            resp = await client.get(url, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("hydra:member", []) or data.get("data", [])
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener RUG.")
        except Exception as e:
            logger.error(f"Error fetching RUG records: {e}")
        return []
    
    async def get_invoice_totals_by_rfc(self, client: httpx.AsyncClient, entity_id: str, rfc_contraparte: str, as_receiver: bool) -> float:
        """
        as_receiver=True -> Facturas donde la contraparte es RECEPTOR (Facturas Emitidas por nosotros).
        as_receiver=False -> Facturas donde la contraparte es EMISOR (Facturas Recibidas por nosotros).
        """
        try:
            # Si as_receiver es True, buscamos las facturas que le emitimos a esa contraparte
            param_key = "receiver.rfc" if as_receiver else "issuer.rfc"
            
            # Usamos property filtering para que la API no nos mande los XML completos, solo el total
            params = {
                param_key: rfc_contraparte,
                "properties[]": "total",
                "itemsPerPage": 500  # Un número alto para traer todo rápido
            }
            url = f"{self.base_url}/entities/{entity_id}/invoices"
            resp = await client.get(url, params=params, headers=self.headers)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("hydra:member", [])
                
                # Sumamos el campo 'total' de todas las facturas encontradas
                return sum(float(i.get("total", 0.0)) for i in items if isinstance(i, dict))
            else:
                logger.warning(f"Error HTTP {resp.status_code} al obtener facturas de {rfc_contraparte}.")
                
        except Exception as e:
            logger.error(f"Error sumando facturas para 69-B ({rfc_contraparte}): {e}")
            
        return 0.0

    async def download_file_content(self, client: httpx.AsyncClient, file_id: str) -> bytes:
        """
        Descarga el contenido crudo (bytes) de un archivo en Syntage.
        Útil para pasar PDFs directamente a la IA.
        """
        if not file_id: return b""
        
        try:
            url = f"{self.base_url}/files/{file_id}/download"
            # Aquí usamos el cliente para traer el contenido binario
            resp = await client.get(url, headers=self.headers)
            
            if resp.status_code == 200:
                return resp.content # Retorna los bytes del PDF
            else:
                logger.warning(f"Error HTTP {resp.status_code} al descargar file {file_id}")
        except Exception as e:
            logger.error(f"Error downloading file {file_id}: {e}")
            
        return b""
    
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