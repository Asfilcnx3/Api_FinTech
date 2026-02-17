"""
Script de diagnóstico: muestra la distribución real de X de todos los montos
en las páginas de movimientos del PDF, sin ningún filtro.
Corre esto una vez para ver dónde caen realmente los números.
"""
import fitz
import re
from collections import defaultdict

PDF_PATH = r"C:\Users\sosbr\Documents\FastAPI\docker-fluxo-api\fluxo-api\ABRIL 2025.pdf"
REGEX_MONTO = re.compile(r'^\d{1,3}(?:,\d{3})*\.\d{2}$')

def bucketear(x, tam_bucket=5):
    return round(x / tam_bucket) * tam_bucket

with fitz.open(PDF_PATH) as doc:
    for num_pag in range(1, min(5, len(doc) + 2)):
        page = doc[num_pag - 1]
        ancho = page.rect.width
        words = page.get_text("words")

        # Solo zona derecha (donde están las columnas numéricas)
        montos = [
            w for w in words
            if REGEX_MONTO.match(w[4].replace("$", "").replace(",", ""))
            and (w[0] + w[2]) / 2 > ancho * 0.30   # mitad derecha
        ]

        if not montos:
            continue

        print(f"\n{'='*60}")
        print(f"PÁGINA {num_pag} — {len(montos)} montos encontrados")
        print(f"{'='*60}")

        # Agrupar por bucket de X
        buckets = defaultdict(list)
        for w in montos:
            x_centro = (w[0] + w[2]) / 2
            b = bucketear(x_centro)
            buckets[b].append((x_centro, w[4], w[1]))  # x, texto, y

        # Mostrar en orden de X
        print(f"\n{'X_BUCKET':>10} | {'COUNT':>5} | {'VALORES (x, texto)':}")
        print("-" * 70)
        for b in sorted(buckets.keys()):
            items = buckets[b]
            muestras = [(f"x={x:.1f}:{txt}" ) for x, txt, _ in items[:4]]
            print(f"{b:>10} | {len(items):>5} | {', '.join(muestras)}")

        # Resumen: clusters principales
        print(f"\n📊 CLUSTERS PRINCIPALES (buckets con ≥3 valores):")
        for b in sorted(buckets.keys()):
            if len(buckets[b]) >= 3:
                xs = [x for x, _, _ in buckets[b]]
                avg = sum(xs) / len(xs)
                muestras_txt = [txt for _, txt, _ in buckets[b][:5]]
                print(f"   X≈{avg:.1f} ({len(buckets[b])} montos): {muestras_txt}")

        # Mostrar montos específicos problemáticos
        print(f"\n🔍 MONTOS PROBLEMÁTICOS (17,242.00 y 12,000.00):")
        for w in words:
            txt = w[4]
            if txt in ["17,242.00", "12,000.00"]:
                x_c = (w[0] + w[2]) / 2
                print(f"   '{txt}' → x0={w[0]:.1f}, x1={w[2]:.1f}, x_centro={x_c:.1f}, y={w[1]:.1f}")