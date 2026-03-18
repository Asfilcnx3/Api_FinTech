import logging
import re
from typing import Dict, Any
from ....models.responses_precalificacion import PrequalificationResponse

logger = logging.getLogger(__name__)

class RegistryProcessor:
    """
    Procesa la información legal y registral (RPC y RUG).
    """
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"[{raw_data.get('rfc')}] Procesando Registros Públicos (RPC y RUG)...")
        
        raw_rpc = raw_data.get("raw_rpc", [])
        raw_rug = raw_data.get("raw_rug", [])
        
        # Blindaje contra formatos inesperados
        if not isinstance(raw_rpc, list): raw_rpc = []
        if not isinstance(raw_rug, list): raw_rug = []
        
        # 1. Parsear RPC (Estructura real)
        rpc_records = []
        for item in raw_rpc:
            if not isinstance(item, dict): continue
            
            # A. Extraer Socios (Buscamos en plural y singular por seguridad)
            raw_socios = item.get("socios") or item.get("socio") or []
            socios_list = []
            for socio in raw_socios:
                if not isinstance(socio, dict): continue
                
                # Unimos nombre, paterno y materno por si vienen separados
                n_str = f"{socio.get('nombre', '')} {socio.get('apellidoPaterno', '')} {socio.get('apellidoMaterno', '')}".strip()
                if not n_str: n_str = "N/A"
                
                try: valor_acc = float(socio.get("valor") or 0.0)
                except: valor_acc = 0.0
                
                socios_list.append(PrequalificationResponse.RpcSocio(
                    name=n_str,
                    shares=str(socio.get("acciones", "N/A")),
                    value=valor_acc,
                    status=str(socio.get("estatus", "N/A"))
                ))
                
            # B. Extraer Actos (Buscamos en plural y singular por seguridad)
            raw_actos = item.get("actos") or item.get("acto") or []
            actos_list = []
            for acto in raw_actos:
                if not isinstance(acto, dict): continue
                
                actos_list.append(PrequalificationResponse.RpcActo(
                    date=str(acto.get("fechaDeInscripcion") or acto.get("fechaDeIngreso") or "N/A")[:10],
                    description=str(acto.get("formaPrecodificada") or acto.get("acto") or "N/A"),
                    document_number=str(acto.get("numeroDeDocumento", "N/A"))
                ))

            # C. Guardar registro completo
            rpc_records.append(PrequalificationResponse.RpcRecord(
                folio_mercantil=str(item.get("fme", "N/A")),
                date=str(item.get("fechaDeInscripcion", "N/A"))[:10],
                state=str(item.get("entidadFederativa", "N/A")),
                business_name=str(item.get("nombreRazonSocial", "N/A")),
                socios=socios_list,
                actos=actos_list
            ))
            
        # 2. Parsear RUG (Estructura real anidada)
        rug_records = []
        for item in raw_rug:
            if not isinstance(item, dict): continue
            
            boleta = item.get("boleta", {})
            if not isinstance(boleta, dict): boleta = {}
                
            datos_asiento = boleta.get("datos_del_asiento", {})
            datos_acreedor = boleta.get("datos_del_acreedor", {})
            datos_garantia = boleta.get("datos_de_la_garantia_mobiliaria", {})
            
            # Limpieza del monto (ej: "$ 12345.67 Peso Mexicano" -> 12345.67)
            monto_str = str(datos_garantia.get("monto_maximo_garantizado_y_moneda", "0"))
            monto = 0.0
            moneda = "MXN"
            
            match = re.search(r'[\d,]+\.?\d*', monto_str)
            if match:
                num_str = match.group().replace(",", "")
                try: monto = float(num_str)
                except: pass
                
            # Si dice Dolar o USD, cambiamos la moneda
            if "dolar" in monto_str.lower() or "usd" in monto_str.lower():
                moneda = "USD"
                
            rug_records.append(PrequalificationResponse.RugRecord(
                guarantee_number=str(item.get("numeroDeGarantia", "N/A")),
                creation_date=str(item.get("fecha", "N/A"))[:10], # Cortamos la fecha a YYYY-MM-DD
                validity_date=str(datos_asiento.get("vigencia", "N/A")),
                creditor=str(datos_acreedor.get("nombre_denominacion_o_razon_social", "N/A")),
                amount=monto,
                currency=moneda,
                status=str(item.get("tipo", "N/A")).capitalize()
            ))
            
        return {
            "registry_data": PrequalificationResponse.RegistryData(
                rpc_records=rpc_records,
                rug_records=rug_records
            )
        }