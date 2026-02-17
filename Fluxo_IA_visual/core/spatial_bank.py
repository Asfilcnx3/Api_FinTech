import fitz  # PyMuPDF
import re
import time
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# ==============================================================================
# 1. MOCK DE MODELOS (Para que funcione sin tus archivos externos)
# ==============================================================================
class RespuestasMotorEstados:
    class TipoTransaccion(Enum):
        CARGO = "cargo"
        ABONO = "abono"
        INDEFINIDO = "indefinido"
        SALDO = "saldo"

    class MetodoExtraccion(Enum):
        EXACTO_GEO_COLUMNA = "OK_SPATIAL_CLASS"

    @dataclass
    class TransaccionDetectada:
        fecha: str
        descripcion: str
        monto: float
        tipo: Any
        id_interno: str
        score_confianza: float
        metodo_match: Any
        coords_box: Optional[List[float]] = None
        errores: List[str] = field(default_factory=list)

    @dataclass
    class MetricasPagina:
        numero_pagina: int
        tiempo_procesamiento_ms: float
        cantidad_bloques_detectados: int
        cantidad_transacciones_finales: int
        calidad_promedio_pagina: float
        alertas: List[str]

    @dataclass
    class ResultadoPagina:
        pagina: int
        metricas: Any
        transacciones: List[Any]

# ==============================================================================
# 2. MOTOR PRINCIPAL (BankStatementEngine)
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("BankEngine")

@dataclass
class StatementContext:
    columnas_detectadas: Optional[Dict] = None

class BankStatementEngine:
    def __init__(self):
        self.metrics = {
            "total_paginas": 0,
            "total_transacciones": 0,
            "tiempo_total": 0.0
        }
        
        # --- REGEX DE FECHAS MEJORADO ---
        # 1. Flexible: Soporta "01 ABR", "01/04/2025", "18/MAR 18/MAR" (toma el inicio)
        self.REGEX_FECHA_FLEXIBLE = re.compile(
            r"^\d{1,2}[\s/-](?:[a-zA-Z]{3}|\d{2})(?:[\s/-]\d{2,4})?", 
            re.IGNORECASE
        )
        
        # 2. Solo Día: Soporta "02", "13" (Estricto 1-2 dígitos)
        self.REGEX_SOLO_DIA = re.compile(r"^\d{1,2}$")
        
        # KEYWORDS
        self.KEYWORDS_HEADER_FECHA = ["fecha", "dia", "día", "date", "fech", "operación", "operacion"]
        self.TRIGGERS_CIERRE = [
            "total de movimientos", "total de cargos", "total de abonos",
            "resumen de comisiones", "cadena original", "timbre fiscal", 
            "este documento es una representación", "saldo final del periodo"
        ]
        
        self.KEYWORDS_CARGO = ["retiro", "retiros", "cargo", "cargos", "debito", "debitos", "débito", "signo", "debe", "salida"]
        self.KEYWORDS_ABONO = ["deposito", "depositos", "depósito", "abono", "abonos", "credito", "creditos", "haber", "entrada"]
        self.KEYWORDS_IGNORE_DESC = [
            "saldo anterior", "saldo inicial", "saldo al corte", 
            "saldo promedio", "total de", "resumen de", "no. de cuenta", "saldo"
        ]

    # -------------------------------------------------------------------------
    # PIPELINE "PERGAMINO INFINITO" (Concatenación Vertical)
    # -------------------------------------------------------------------------
    def procesar_documento_entero(self, pdf_path: str) -> List[RespuestasMotorEstados.ResultadoPagina]:
        t_start_global = time.time()
        resultados_totales = []
        all_words_continuos = []
        y_offset_acumulado = 0.0
        ctx = StatementContext()

        try:
            with fitz.open(pdf_path) as doc:
                if len(doc) == 0: return []
                
                # Detectar columnas solo UNA VEZ (Página 1)
                ancho_pagina = doc[0].rect.width
                zonas_x = self._detectar_zonas_columnas(doc[0])
                ctx.columnas_detectadas = zonas_x

                for i, page in enumerate(doc):
                    alto_pagina = page.rect.height
                    y_hard_stop = self._calcular_hard_stop(page)
                    
                    # Ignorar header repetitivo en páginas 2+
                    y_start = alto_pagina * 0.15 if i > 0 else 0
                    
                    rect_lectura = fitz.Rect(0, y_start, ancho_pagina, y_hard_stop)
                    words = page.get_text("words", clip=rect_lectura)
                    
                    # STITCHING: Ajustar coordenada Y
                    words_ajustados = []
                    for w in words:
                        w_list = list(w)
                        w_list[1] += y_offset_acumulado # Y0
                        w_list[3] += y_offset_acumulado # Y1
                        words_ajustados.append(w_list)
                    
                    all_words_continuos.extend(words_ajustados)
                    y_offset_acumulado += alto_pagina

                # PROCESAMIENTO ÚNICO
                anclas = self._encontrar_anclas_fechas(all_words_continuos, ancho_pagina)
                transacciones = self._extraer_transacciones_por_slice(
                    anclas, all_words_continuos, zonas_x, y_offset_acumulado
                )
                
                # EMPAQUETADO
                tiempo_ms = (time.time() - t_start_global) * 1000
                metricas = RespuestasMotorEstados.MetricasPagina(
                    numero_pagina=999,
                    tiempo_procesamiento_ms=round(tiempo_ms, 2),
                    cantidad_bloques_detectados=len(transacciones),
                    cantidad_transacciones_finales=len(transacciones),
                    calidad_promedio_pagina=1.0,
                    alertas=[]
                )
                
                resultados_totales.append(RespuestasMotorEstados.ResultadoPagina(
                    pagina=999, metricas=metricas, transacciones=transacciones
                ))

        except Exception as e:
            logger.error(f"❌ Error crítico: {e}")
            return []

        return resultados_totales

    # -------------------------------------------------------------------------
    # LÓGICA DE DETECCIÓN
    # -------------------------------------------------------------------------
    def _calcular_hard_stop(self, page: fitz.Page) -> float:
        texto_lower = page.get_text("text").lower()
        y_limite = page.rect.height
        for trigger in self.TRIGGERS_CIERRE:
            if trigger in texto_lower:
                instancias = page.search_for(trigger)
                if instancias:
                    y_limite = min(y_limite, instancias[0].y0 - 5)
        return y_limite

    def _detectar_zonas_columnas(self, page: fitz.Page) -> Dict:
        """ LÓGICA MIDPOINT (Corrige BBVA y Banamex) """
        ancho = page.rect.width
        rect_header = fitz.Rect(0, 0, ancho, page.rect.height * 0.35)
        words = page.get_text("words", clip=rect_header)
        
        x_saldo_header = None
        coords = {"cargo": None, "abono": None}
        
        for w in words:
            texto = w[4].lower().strip().replace(".", "").replace(":", "")
            x_left = w[0]
            x_center = (w[0] + w[2]) / 2
            
            if any(k == texto for k in self.KEYWORDS_CARGO): # Match estricto primero
                if not coords["cargo"]: coords["cargo"] = x_center
            elif any(k in texto for k in self.KEYWORDS_ABONO):
                if not coords["abono"]: coords["abono"] = x_center
            elif "saldo" in texto and x_left > (ancho * 0.70):
                if not x_saldo_header: x_saldo_header = x_left

        # Definir Muro Derecho (Saldo)
        muro_derecho = x_saldo_header - 10 if x_saldo_header else ancho * 0.90

        # Definir Frontera Central (PUNTO MEDIO)
        if coords["cargo"] and coords["abono"]:
            frontera_central = (coords["cargo"] + coords["abono"]) / 2
        elif coords["abono"]:
            frontera_central = coords["abono"] - 40
        elif coords["cargo"]:
            frontera_central = coords["cargo"] + 40
        else:
            frontera_central = ancho * 0.65 # Fallback BBVA

        # Construir Rangos
        start_cargo = coords["cargo"] - 60 if coords["cargo"] else (ancho * 0.40)
        
        r_cargo = (start_cargo, frontera_central)
        r_abono = (frontera_central, muro_derecho)
        r_saldo = (muro_derecho, ancho)

        logger.info(f"📍 Geometría: Cargo[{r_cargo[0]:.0f}-{r_cargo[1]:.0f}] | Abono[{r_abono[0]:.0f}-{r_abono[1]:.0f}]")
        return {"cargo": r_cargo, "abono": r_abono, "saldo": r_saldo, "muro_derecho": muro_derecho}

    def _encontrar_anclas_fechas(self, words: List, ancho_pagina: float) -> List[Dict]:
        """ Soporta Fechas Dobles y 'Solo Día' (Afirme/Santander) """
        x_pared = 40.0 # Default
        
        # Detectar pared dinámica
        for w in sorted(words[:100], key=lambda x: x[1]):
            if w[0] < (ancho_pagina * 0.30):
                if w[4].upper().replace(":","") in self.KEYWORDS_HEADER_FECHA:
                    x_pared = w[0] + 50.0
                    break
        
        # Filtrar candidatos izquierda
        candidatos = [w for w in words if w[0] < x_pared]
        candidatos.sort(key=lambda w: (round(w[1], 1), w[0]))
        
        anclas = []
        if not candidatos: return []
        
        # Agrupar visualmente
        lineas_agrupadas = []
        linea_actual = {"txt": candidatos[0][4], "y": candidatos[0][1], "x": candidatos[0][0], "tokens": [candidatos[0]]}
        
        for w in candidatos[1:]:
            if abs(w[1] - linea_actual["y"]) < 5:
                linea_actual["txt"] += " " + w[4]
                linea_actual["tokens"].append(w)
            else:
                lineas_agrupadas.append(linea_actual)
                linea_actual = {"txt": w[4], "y": w[1], "x": w[0], "tokens": [w]}
        lineas_agrupadas.append(linea_actual)
        
        # Análisis
        for linea in lineas_agrupadas:
            raw = linea["txt"].strip()
            primer_token = linea["tokens"][0][4].strip()
            
            # Caso 1: Fecha Completa (o Doble)
            match_flex = self.REGEX_FECHA_FLEXIBLE.match(raw)
            if match_flex:
                anclas.append({"texto_fecha": match_flex.group(0), "y_anchor": linea["y"], "x_start": linea["x"]})
                continue
                
            # Caso 2: Solo Día (02, 13)
            match_dia = self.REGEX_SOLO_DIA.match(primer_token)
            if match_dia:
                try:
                    dia = int(primer_token)
                    if 1 <= dia <= 31 and linea["x"] < (x_pared - 10):
                        anclas.append({"texto_fecha": str(dia), "y_anchor": linea["y"], "x_start": linea["x"]})
                except: pass
                
        return anclas

    def _extraer_transacciones_por_slice(
        self, anclas: List[Dict], words: List, zonas_x: Dict, y_limite_total: float
    ) -> List[RespuestasMotorEstados.TransaccionDetectada]:
        
        transacciones = []
        x_muro = zonas_x.get("muro_derecho", 10000.0)
        
        for i, ancla in enumerate(anclas):
            y_techo = ancla["y_anchor"] - 2
            y_suelo_ref = anclas[i+1]["y_anchor"] - 2 if i < len(anclas) - 1 else y_limite_total
            y_suelo = min(y_suelo_ref, y_limite_total)
            
            palabras_slice = [w for w in words if y_techo <= w[1] < y_suelo]
            
            desc_tokens = []
            cand_montos = []
            x_inicio_desc = ancla["x_start"] + 35 
            x_fin_desc = zonas_x["cargo"][0] - 10 
            
            for w in palabras_slice:
                x, y, _, _, texto = w[:5]
                
                if x < x_inicio_desc: continue 
                if x >= x_muro: continue # Muro de Saldo
                
                clean_txt = texto.replace("$", "").replace(",", "")
                # Regex numérico robusto
                es_numero = re.search(r'^\d{1,3}(?:,\d{3})*\.\d{2}$', clean_txt) or \
                            (re.search(r'\d', clean_txt) and "." in clean_txt and len(clean_txt) < 15)

                if x < x_fin_desc:
                    desc_tokens.append(w)
                else:
                    col = RespuestasMotorEstados.TipoTransaccion.INDEFINIDO
                    if zonas_x["cargo"][0] <= x <= zonas_x["cargo"][1]: 
                        col = RespuestasMotorEstados.TipoTransaccion.CARGO
                    elif zonas_x["abono"][0] <= x <= zonas_x["abono"][1]: 
                        col = RespuestasMotorEstados.TipoTransaccion.ABONO
                    
                    if es_numero:
                        try:
                            val = float(clean_txt)
                            cand_montos.append({"val": val, "x": x, "col": col, "box": w[:4]})
                        except: pass
                    elif x < (x_fin_desc + 120): # Tolerancia para descripciones largas
                        desc_tokens.append(w)
            
            desc_tokens.sort(key=lambda w: (round(w[1], 0), w[0]))
            desc_str = " ".join([w[4] for w in desc_tokens])
            
            # Filtro Semántico (Ignorar "SALDO ANTERIOR" si no tiene monto asociado)
            desc_clean = " ".join(desc_str.split()).upper()
            if any(k.upper() in desc_clean for k in self.KEYWORDS_IGNORE_DESC):
                continue

            # Selección Monto
            movs = [m for m in cand_montos if m["col"] in [RespuestasMotorEstados.TipoTransaccion.CARGO, RespuestasMotorEstados.TipoTransaccion.ABONO]]
            
            if movs:
                mejor = sorted(movs, key=lambda k: k["x"])[0]
                monto_final = mejor["val"]
                tipo_final = mejor["col"]
            else:
                continue

            tx = RespuestasMotorEstados.TransaccionDetectada(
                fecha=ancla["texto_fecha"],
                descripcion=desc_str,
                monto=monto_final,
                tipo=tipo_final,
                id_interno=f"Y{int(ancla['y_anchor'])}",
                score_confianza=0.95,
                metodo_match=RespuestasMotorEstados.MetodoExtraccion.EXACTO_GEO_COLUMNA
            )
            transacciones.append(tx)
            
        return transacciones

# ==============================================================================
# 3. EJECUCIÓN DIRECTA
# ==============================================================================

# -------------------------------------------------------------
PDF_PATH = r"C:\\Users\\sosbr\\Documents\\FastAPI\\docker-fluxo-api\\fluxo-api\\ABRIL 2025.pdf"
# -------------------------------------------------------------

def main():
    print(f"🔄 Procesando: {PDF_PATH}")
    engine = BankStatementEngine()
    
    resultados = engine.procesar_documento_entero(PDF_PATH)
    
    if not resultados:
        print("❌ No se obtuvieron resultados.")
        return

    # IMPRIMIR REPORTE IGUAL QUE ANTES
    res = resultados[0] # Al ser 'infinito', todo está en el índice 0
    
    print(f"\n✅ REPORTE FINAL ({res.metricas.cantidad_transacciones_finales} transacciones)")
    header = f"   {'ID':<8} | {'FECHA':<10} | {'MONTO':>12} | {'TIPO':<8} | {'DESCRIPCIÓN'}"
    print("-" * 120)
    print(header)
    print("-" * 120)
    
    abonos = 0
    cargos = 0
    
    for tx in res.transacciones:
        tipo_str = tx.tipo.value if hasattr(tx.tipo, 'value') else str(tx.tipo)
        if "abono" in tipo_str: abonos += 1
        if "cargo" in tipo_str: cargos += 1
        
        desc_fmt = (tx.descripcion[:60] + '..') if len(tx.descripcion) > 60 else tx.descripcion
        print(f"   {tx.id_interno:<8} | {tx.fecha:<10} | {tx.monto:,.2f} | {tipo_str:<8} | {desc_fmt}")

    print("-" * 120)
    print(f"📊 RESUMEN: Cargos: {cargos} | Abonos: {abonos}")

if __name__ == "__main__":
    main()