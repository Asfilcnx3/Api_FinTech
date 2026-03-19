# Fluxo_IA_visual/services/prequalification/processors/risk_processor.py
from typing import Dict, Any, List
import logging
import json
from ....models.responses_precalificacion import PrequalificationResponse
from ...ia_extractor import analizar_gpt_fluxo
from ....utils.helpers_texto_precalificación import prompt_32d

logger = logging.getLogger(__name__)

class RiskProcessor:
    """
    Procesa toda la información relacionada con Riesgos, Credenciales (CIEC, 32-D), Buró y Tamaño (Empleados).
    """
    async def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Riesgos, Credenciales, Empleados y Lista Negra...")
        
        ciec_data = raw_data.get("ciec_data", {})
        buro_data = raw_data.get("buro_data", {})
        compliance_data = raw_data.get("compliance_data", {})
        activities = raw_data.get("activities", [])
        raw_employees = raw_data.get("raw_employees", [])
        raw_blacklist = raw_data.get("raw_blacklist", {}) 
        
        # En caso de que el client devuelva la info envuelta en una lista por accidente
        if isinstance(raw_blacklist, list) and len(raw_blacklist) > 0:
            raw_blacklist = raw_blacklist[0]
        elif not isinstance(raw_blacklist, dict):
            raw_blacklist = {}
        
        # --- PARSEO AGRUPADO DE LISTA NEGRA ---
        dict_counterparties = {}

        for category in ["issued", "received"]:
            items = raw_blacklist.get(category, [])
            if not isinstance(items, list): continue
                
            for item in items:
                if not isinstance(item, dict): continue
                    
                taxpayer = item.get("taxpayer", {})
                if not isinstance(taxpayer, dict): continue

                rfc_val = taxpayer.get("rfc", "N/A")
                if rfc_val == "N/A": continue
                
                # Inicializamos al facturero si es la primera vez que lo vemos
                if rfc_val not in dict_counterparties:
                    dict_counterparties[rfc_val] = {
                        "name": taxpayer.get("name") or taxpayer.get("razonSocial") or taxpayer.get("businessName") or "N/A",
                        "status": taxpayer.get("blacklistStatus", "N/A"),
                        "issued_count": 0,
                        "issued_amount": 0.0,
                        "received_count": 0,
                        "received_amount": 0.0
                    }
                
                # Extraemos las facturas y el monto que la OLA 3 nos inyectó
                count = int(item.get("invoices", 0))
                monto = float(item.get("monto_acumulado", 0.0))
                
                # Sumamos a la cubeta correspondiente
                if category == "issued":
                    dict_counterparties[rfc_val]["issued_count"] += count
                    dict_counterparties[rfc_val]["issued_amount"] += monto
                else:
                    dict_counterparties[rfc_val]["received_count"] += count
                    dict_counterparties[rfc_val]["received_amount"] += monto

        # Convertimos el diccionario agrupado al modelo Pydantic
        blacklisted_counterparties = [
            PrequalificationResponse.BlacklistedCounterparty(
                rfc=rfc,
                **datos
            ) for rfc, datos in dict_counterparties.items()
        ]

        # --- 2. ANÁLISIS DEL PDF 32-D CON IA ---
        raw_compliance_pdf = raw_data.get("raw_compliance_pdf", b"")
        
        # Estructura por defecto en caso de fallo o falta de PDF
        analisis_32d_dict = {
            "opinion_ia": "El archivo PDF no estuvo disponible para su análisis.",
            "obligaciones_omitidas": []
        }
        
        if raw_compliance_pdf:
            logger.info(f"[{raw_data.get('rfc')}] PDF de 32-D descargado. Enviando a GPT Vision...")

            try:
                # Le pasamos la página 1 a GPT
                respuesta_llm = await analizar_gpt_fluxo(prompt_32d, raw_compliance_pdf, paginas_a_procesar=[1], razonamiento="low")

                # Log momentaneo
                # logger.info(f"Trace respuesta_llm: {respuesta_llm}")
                
                # Limpiamos los backticks de markdown (```json ... ```) por si GPT los incluye
                respuesta_limpia = respuesta_llm.replace("```json", "").replace("```", "").strip()
                
                # Convertimos el string a Diccionario
                analisis_32d_dict = json.loads(respuesta_limpia)
                
            except Exception as e:
                logger.error(f"Error en LLM 32-D: {e}")
                analisis_32d_dict["opinion_ia"] = "No se pudo generar el análisis estructurado debido a un error de Inteligencia Artificial."

        # Mapeamos al objeto Pydantic
        compliance_llm_data = PrequalificationResponse.ComplianceLLMData(
            opinion_ia=analisis_32d_dict.get("opinion_ia", "Sin opinión."),
            obligaciones_omitidas=[
                PrequalificationResponse.ObligacionOmitida(**obl) 
                for obl in analisis_32d_dict.get("obligaciones_omitidas", [])
            ]
        )

        return {
            "economic_activities": [
                PrequalificationResponse.EconomicActivity(**act) for act in activities
            ],
            "risk_indicators": raw_data.get("risks", []),
            "employee_metrics": self._process_employees(raw_employees),
            "blacklisted_counterparties": blacklisted_counterparties,
            
            "ciec_info": PrequalificationResponse.CredentialInfo(
                status=ciec_data.get("status", "unknown"),
                last_check_date=ciec_data.get("date"),
                last_extraction_date=ciec_data.get("last_extraction_date")
            ),
            
            "buro_info": PrequalificationResponse.BuroInfo(
                has_report=buro_data.get("has_report", False),
                status=buro_data.get("status", "unknown"),
                score=buro_data.get("score"),
                last_check_date=buro_data.get("date"),
                credit_lines=buro_data.get("credit_lines", []), 
                inquiries=buro_data.get("inquiries", []),
                inquiries_summary=buro_data.get("inquiries_summary", []),
                summary_metrics=buro_data.get("summary_metrics"),
                raw_buro_data=buro_data.get("raw_buro_data", {})    
            ),
            
            "compliance_opinion": PrequalificationResponse.CredentialInfo(
                status=compliance_data.get("status", "unknown"),
                last_check_date=compliance_data.get("date")
            ),
            "compliance_llm_data": compliance_llm_data
        }

    def _process_employees(self, raw_employees: List[Dict]) -> PrequalificationResponse.EmployeeMetrics:
        # --- LOG DE DEBUG 2: ENTRADA AL PROCESADOR ---
        # logger.info(f"DEBUG EMPLEADOS (PROCESADOR): Recibí raw_employees con {len(raw_employees)} elementos.")
        
        if not raw_employees:
            return PrequalificationResponse.EmployeeMetrics()

        # Ordenar cronológicamente (más antiguo primero)
        sorted_emp = sorted(raw_employees, key=lambda x: x.get("date", ""))
        
        history = [
            PrequalificationResponse.EmployeeHistoryItem(date=e.get("date"), total=int(e.get("total", 0))) 
            for e in sorted_emp
        ]
        
        # --- LOG DE DEBUG 3: HISTORIAL ORDENADO ---
        # fechas = [h.date for h in history]
        # logger.info(f"DEBUG EMPLEADOS (HISTORIAL): Fechas ordenadas: {fechas[-5:]} (mostrando últimas 5)")

        # Helper para encontrar el valor buscando hacia atrás en la lista
        # (Syntage manda los meses consecutivos, por lo que el índice hacia atrás es confiable)
        def get_val_by_offset(months_back: int) -> int | None:
            idx = len(history) - 1 - months_back
            if 0 <= idx < len(history):
                return history[idx].total
            return None

        # Extraer las cubetas: Mes Actual = offset 0, Hace 3 meses = offset 2, etc.
        v_1 = get_val_by_offset(0)
        v_3 = get_val_by_offset(2)
        v_6 = get_val_by_offset(5)
        v_9 = get_val_by_offset(8)
        v_12 = get_val_by_offset(11)
        v_24 = get_val_by_offset(23)

        def make_period(curr_val, prev_val):
            if curr_val is None:
                return None
            p = PrequalificationResponse.EmployeePeriod(total=curr_val)
            if prev_val is not None:
                diff = curr_val - prev_val
                p.difference = diff
                if diff > 0: p.trend_text = "Aumentó"
                elif diff < 0: p.trend_text = "Disminuyó"
                else: p.trend_text = "Constante"
            else:
                p.trend_text = "Sin datos previos"
                p.difference = 0
            return p

        # Comparaciones escalonadas de abajo hacia arriba
        p_24 = make_period(v_24, None)
        p_12 = make_period(v_12, v_24)
        p_9 = make_period(v_9, v_12)
        p_6 = make_period(v_6, v_9)
        p_3 = make_period(v_3, v_6)
        p_1 = make_period(v_1, v_3)

        return PrequalificationResponse.EmployeeMetrics(
            current_total=v_1 or 0,
            month_24=p_24,
            month_12=p_12,
            month_9=p_9,
            month_6=p_6,
            month_3=p_3,
            month_1=p_1,
            history=history
        )