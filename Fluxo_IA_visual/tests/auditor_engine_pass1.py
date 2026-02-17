import time
import json
import logging
import os
from datetime import datetime
from dataclasses import asdict, is_dataclass

# --- IMPORTA TU MOTOR AQUÍ ---
# Asegúrate de que el archivo donde está BankStatementEngineV2 se llame 'engine_v2.py' 
# o cambia el nombre aquí abajo.
from engine_v2 import BankStatementEngineV2, ColumnLayout, PageGeometry 
import fitz

# Configuración de Logs para que se vea limpio en consola
logging.basicConfig(level=logging.ERROR) # Solo errores del motor, el resto lo imprime el script
logger = logging.getLogger("AuditTool")

class AuditEncoder(json.JSONEncoder):
    """Ayuda a guardar las Dataclasses (Layouts/Geometry) en el JSON"""
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, fitz.Rect):
            return [obj.x0, obj.y0, obj.x1, obj.y1]
        return super().default(obj)

def run_audit(pdf_path: str):
    print(f"============================================================")
    print(f"   AUDITORÍA PROFUNDA MOTOR V2 (3-PASS ARCHITECTURE)")
    print(f"   Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Archivo: {os.path.basename(pdf_path)}")
    print(f"============================================================\n")

    if not os.path.exists(pdf_path):
        print(f"❌ ERROR: El archivo no existe: {pdf_path}")
        return

    # 1. INICIALIZACIÓN
    t_start_load = time.time()
    engine = BankStatementEngineV2()
    doc = fitz.open(pdf_path)
    t_load = (time.time() - t_start_load) * 1000

    print(f"⏱️  Carga de PDF y Motor: {t_load:.2f} ms")

    # ---------------------------------------------------------
    # PASADA 1: GEOMETRÍA
    # ---------------------------------------------------------
    t0 = time.time()
    geometries = engine.pass_1_detect_geometry(doc)
    t1 = time.time()
    time_p1 = (t1 - t0) * 1000
    print(f"🔹 Pasada 1 (Geometría Y)   : {time_p1:.2f} ms | {len(geometries)} páginas analizadas")

    # ---------------------------------------------------------
    # PASADA 2: COLUMNAS
    # ---------------------------------------------------------
    t0 = time.time()
    layouts = engine.pass_2_detect_columns(doc, geometries)
    t1 = time.time()
    time_p2 = (t1 - t0) * 1000
    
    # Análisis rápido de Layouts
    layouts_ok = sum(1 for l in layouts if l.has_explicit_headers)
    layouts_inherited = sum(1 for l in layouts if not l.has_explicit_headers and l.columns)
    layouts_failed = len(layouts) - layouts_ok - layouts_inherited
    
    print(f"🔹 Pasada 2 (Columnas X)    : {time_p2:.2f} ms")
    print(f"   └─ Detectados: {layouts_ok} | Heredados: {layouts_inherited} | Fallidos: {layouts_failed}")

    # ---------------------------------------------------------
    # PASADA 3: EXTRACCIÓN
    # ---------------------------------------------------------
    t0 = time.time()
    raw_results = engine.pass_3_extract_rows(doc, geometries, layouts)
    t1 = time.time()
    time_p3 = (t1 - t0) * 1000
    print(f"🔹 Pasada 3 (Slicing & Ext) : {time_p3:.2f} ms")

    # =========================================================================
    #  NUEVO: GENERACIÓN DE PDF VISUAL (DEBUG)
    # =========================================================================
    try:
        debug_filename = f"debug_{os.path.basename(pdf_path)}"
        print(f"🎨 Generando PDF Visual: {debug_filename} ...")
        
        # Llamamos a tu método debug_draw_all
        engine.debug_draw_all(
            doc_path=pdf_path, 
            output_path=debug_filename, 
            geometries=geometries, 
            layouts=layouts, 
            extractions=raw_results
        )
        print(f"   └─ ✅ PDF guardado correctamente.")
    except Exception as e:
        print(f"   └─ ❌ Error generando PDF visual: {e}")
    # =========================================================================

    # ---------------------------------------------------------
    # GENERACIÓN DE REPORTE POR PÁGINA
    # ---------------------------------------------------------
    global_abonos = 0
    global_cargos = 0
    global_transacciones = 0
    full_audit_data = []

    for i, res in enumerate(raw_results):
        page_num = res["page"]
        layout = layouts[i]
        geo = geometries[i]
        txs = res["transacciones"]

        # Métricas de página
        n_cargos = sum(1 for t in txs if t['tipo'] == 'CARGO')
        n_abonos = sum(1 for t in txs if t['tipo'] == 'ABONO')
        global_cargos += n_cargos
        global_abonos += n_abonos
        global_transacciones += len(txs)

        # Estado del Layout
        layout_status = "✅ DETECTADO" if layout.has_explicit_headers else ("⚠️ HEREDADO" if layout.columns else "❌ FALLIDO")
        
        print(f"\n█ PÁGINA {page_num} " + "█" * 60)
        print(f"   [ESTADO DEL MOTOR]")
        print(f"   ├─ Geometría Y   : Header@{geo.header_y:.1f}px | Footer@{geo.footer_y:.1f}px")
        print(f"   ├─ Layout X      : {layout_status}")
        if layout.columns:
            cols_str = ", ".join(layout.columns.keys())
            print(f"   ├─ Columnas      : [{cols_str}]")
        print(f"   └─ Transacciones : {len(txs)} (Cargos: {n_cargos}, Abonos: {n_abonos})")

        # TABLA DE DATOS
        print(f"\n   [DETALLE DE EXTRACCIÓN]")
        header_fmt = f"   {'FECHA':<8} | {'TIPO':<7} | {'MONTO':>12} | {'DESCRIPCIÓN (STITCHING CHECK)'}"
        print("   " + "-" * 100)
        print(header_fmt)
        print("   " + "-" * 100)

        for tx in txs:
            # Formateo
            monto_str = f"${tx['monto']:,.2f}"
            tipo_short = tx['tipo'][:5]
            
            # Limpieza de descripción para visualización
            # Aquí es donde veremos si el stitching funcionó
            desc_clean = tx['descripcion'].replace('\n', ' ').strip()
            if len(desc_clean) > 65:
                desc_clean = desc_clean[:62] + "..."
            
            # Alerta visual si la descripción es muy corta (posible error de stitching)
            warning = "⚠️ CORTO" if len(desc_clean) < 5 else ""
            
            print(f"   {tx['fecha']:<8} | {tipo_short:<7} | {monto_str:>12} | {desc_clean} {warning}")

        # Guardar para JSON
        full_audit_data.append({
            "page": page_num,
            "metrics": {
                "layout_status": layout_status,
                "header_y": geo.header_y,
                "count": len(txs)
            },
            "transactions": txs
        })

    # ---------------------------------------------------------
    # RESUMEN FINAL
    # ---------------------------------------------------------
    total_time = t_load + time_p1 + time_p2 + time_p3
    
    print("\n" + "=" * 80)
    print(f"   RESUMEN EJECUTIVO")
    print(f"   Total Transacciones : {global_transacciones}")
    print(f"   Total Cargos        : {global_cargos}")
    print(f"   Total Abonos        : {global_abonos}")
    print(f"   Tiempo Total        : {total_time/1000:.3f} seg (Motor puro)")
    print("=" * 80)

    # Exportar JSON
    output_json = "audit_result_v2.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            "meta": {
                "file": pdf_path,
                "date": str(datetime.now()),
                "total_time_ms": total_time
            },
            "pages": full_audit_data
        }, f, cls=AuditEncoder, indent=4, ensure_ascii=False)
    
    print(f"\n💾 JSON de Auditoría guardado en: {output_json}")

if __name__ == "__main__":
    # CAMBIA ESTA RUTA POR TU PDF
    PDF_TEST = r"C:\Users\sosbr\Documents\FastAPI\docker-fluxo-api\fluxo-api\abril_2025.pdf"
    run_audit(PDF_TEST)