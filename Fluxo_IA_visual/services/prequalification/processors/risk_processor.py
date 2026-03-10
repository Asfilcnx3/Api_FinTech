# Fluxo_IA_visual/services/prequalification/processors/risk_processor.py
from typing import Dict, Any
import logging
from ....models.responses_precalificacion import PrequalificationResponse

logger = logging.getLogger(__name__)

class RiskProcessor:
    """
    Procesa toda la información relacionada con Riesgos, Credenciales (CIEC, 32-D) y Buró.
    """
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Riesgos y Credenciales...")
        
        ciec_data = raw_data.get("ciec_data", {})
        buro_data = raw_data.get("buro_data", {})
        compliance_data = raw_data.get("compliance_data", {})
        activities = raw_data.get("activities", [])
        
        return {
            "economic_activities": [
                PrequalificationResponse.EconomicActivity(**act) for act in activities
            ],
            "risk_indicators": raw_data.get("risks", []),
            
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
            )
        }