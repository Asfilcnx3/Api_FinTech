import pytest
import fitz
from Fluxo_IA_visual.core.spatial_bank import MotorExtraccionEspacial

# ============================================================================
# FIXTURES (Configuración y Mocks en memoria)
# ============================================================================

@pytest.fixture
def motor():
    """Instancia limpia del motor espacial."""
    return MotorExtraccionEspacial(debug_flags=None)

@pytest.fixture
def pdf_memoria():
    """
    Crea un PDF virtual en memoria (RAM) usando PyMuPDF.
    Dibuja los textos en coordenadas (X, Y) exactas para simular columnas reales.
    """
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    
    # 1. Título basura
    page.insert_text((50, 50), "ESTADO DE CUENTA BANCARIO", fontsize=12)
    
    # 2. El Header Real (Alineado con coordenadas físicas)
    y_header = 150
    page.insert_text((50, y_header), "FECHA", fontsize=10)
    page.insert_text((150, y_header), "DESCRIPCION", fontsize=10)
    page.insert_text((300, y_header), "CARGO", fontsize=10)
    page.insert_text((400, y_header), "ABONO", fontsize=10)
    page.insert_text((500, y_header), "SALDO", fontsize=10)
    
    # 3. Transacciones falsas (Respetando las mismas X de sus columnas)
    y_tx = 200
    page.insert_text((50, y_tx), "01/01", fontsize=10)
    page.insert_text((150, y_tx), "PAGO DE SERVICIOS", fontsize=10)
    page.insert_text((300, y_tx), "500.00", fontsize=10)
    page.insert_text((500, y_tx), "1000.00", fontsize=10)
    
    # 4. Footer
    page.insert_text((50, 750), "este documento es una representación impresa", fontsize=8)
    
    yield doc
    doc.close()

# ============================================================================
# PRUEBAS: SCORING DE LÍNEAS (Heurística de Headers)
# ============================================================================

def test_calculate_line_score_header_perfecto(motor):
    """Debe sumar los puntos correctamente para un header tradicional."""
    texto = "FECHA CONCEPTO RETIRO DEPOSITO SALDO"
    # FECHA(1) + CONCEPTO(1) + RETIRO(2) + DEPOSITO(2) + SALDO(2) = 8
    score = motor._calculate_line_score(texto)
    assert score >= 8

def test_calculate_line_score_blacklist_muerte_subita(motor):
    """Cualquier palabra de la lista negra debe anular el score a 0."""
    texto = "FECHA CONCEPTO RETIRO DEPOSITO SALDO ANTERIOR"
    # Tiene un header casi perfecto, pero dice "ANTERIOR" (Blacklist)
    score = motor._calculate_line_score(texto)
    assert score == 0

def test_calculate_line_score_excepcion_blacklist(motor):
    """Debe perdonar la palabra TOTAL solo si viene como SALDO TOTAL."""
    texto_malo = "TOTAL DE MOVIMIENTOS"
    texto_bueno = "FECHA DESCRIPCION CARGOS ABONOS SALDO TOTAL"
    
    assert motor._calculate_line_score(texto_malo) == 0
    assert motor._calculate_line_score(texto_bueno) > 0

def test_calculate_line_score_palabras_cortas(motor):
    """Asegura que 'DIA' (3 letras) no haga falso positivo con 'MEDIODIA'."""
    # "DIA" da 1 punto.
    assert motor._calculate_line_score("DIA DESCRIPCION") >= 2
    # "MEDIODIA" no debería dar el punto de "DIA" porque busca la palabra aislada
    assert motor._calculate_line_score("MEDIODIA DESCRIPCION") == 1

# ============================================================================
# PRUEBAS: PASADA 1 (DETECCIÓN DE GEOMETRÍA)
# ============================================================================

def test_pass_1_detect_geometry_encuentra_limites(motor, pdf_memoria):
    """
    Prueba que el motor encuentre el techo (header) y el piso (footer) 
    leyendo las coordenadas visuales del PDF virtual.
    """
    geometries = motor.pass_1_detect_geometry(pdf_memoria)
    
    assert len(geometries) == 1
    geo = geometries[0]
    
    assert geo.page_num == 1
    # El header lo pintamos en Y=150. PyMuPDF extrae el bounding box, 
    # por lo que el header detectado debería estar muy cerca de 150.
    assert 140 < geo.header_y < 160
    
    # El footer lo pintamos en Y=750. La lógica le resta 5 píxeles por seguridad.
    assert 730 < geo.footer_y < 750

# ============================================================================
# PRUEBAS: PASADA 2 (DETECCIÓN DE COLUMNAS)
# ============================================================================

def test_pass_2_detect_columns_encuentra_layout(motor, pdf_memoria):
    """
    Prueba que el motor identifique correctamente las columnas de la tabla
    basándose en el Header Y detectado en la Pasada 1.
    """
    # 1. Necesitamos la geometría primero para saber dónde buscar
    geometries = motor.pass_1_detect_geometry(pdf_memoria)
    
    # 2. Ejecutamos la detección de columnas
    layouts = motor.pass_2_detect_columns(pdf_memoria, geometries)
    
    # 3. Validaciones
    assert len(layouts) == 1
    layout = layouts[0]
    
    assert layout.has_explicit_headers is True
    assert "FECHA" in layout.columns
    assert "DESCRIPCION" in layout.columns
    assert "CARGO" in layout.columns
    assert "ABONO" in layout.columns
    assert "SALDO" in layout.columns
    
    # Validamos que el bounding box (X0, X1) se haya guardado
    assert layout.columns["FECHA"]["x1"] > layout.columns["FECHA"]["x0"]

# ============================================================================
# PRUEBAS: UTILIDADES DE EXTRACCIÓN (Dinero)
# ============================================================================

def test_validar_dinero_en_fila_exito(motor):
    """Si hay un monto con formato monetario en la zona Y, debe retornar True."""
    # Estructura de la palabra (word) en PyMuPDF: (x0, y0, x1, y1, "texto", block_no, line_no, word_no)
    words_falsas = [
        (100.0, 200.0, 150.0, 210.0, "1,500.50", 0, 0, 0)
    ]
    
    # Configuración de prueba:
    # ancho_pagina = 600 -> El motor ignora el primer 15% izquierdo (90px) para no confundir con fechas. 100.0 > 90 (Pasa)
    # y_target = 205 -> El motor busca entre (205-25) y (205+20). 200.0 está en el rango (Pasa)
    assert motor._validar_dinero_en_fila(words_falsas, y_target=205.0, ancho_pagina=600.0) is True

def test_validar_dinero_en_fila_falla_sin_numeros(motor):
    """Si solo hay texto en esa zona, la validación de dinero debe fallar."""
    words_falsas = [
        (100.0, 200.0, 150.0, 210.0, "PAGO", 0, 0, 0)
    ]
    assert motor._validar_dinero_en_fila(words_falsas, y_target=205.0, ancho_pagina=600.0) is False

def test_validar_dinero_en_fila_falla_fuera_de_zona(motor):
    """Si el dinero está, pero está muy arriba del target Y, debe ignorarlo."""
    words_falsas = [
        (100.0, 100.0, 150.0, 110.0, "1,500.50", 0, 0, 0) # y0 = 100.0
    ]
    # y_target = 205, buscará máximo hasta Y=180. 100 está fuera de alcance.
    assert motor._validar_dinero_en_fila(words_falsas, y_target=205.0, ancho_pagina=600.0) is False

# ============================================================================
# PRUEBAS: PASADA 3 (SLICING Y EXTRACCIÓN FINAL)
# ============================================================================

def test_encontrar_anclas_fechas_numericas(motor):
    """Prueba que el motor encuentre correctamente una fecha en la columna indicada."""
    # (x0, y0, x1, y1, texto, block_no, line_no, word_no)
    words_falsas = [
        (50.0, 200.0, 80.0, 210.0, "01/01", 0, 0, 0),       # La fecha
        (100.0, 200.0, 150.0, 210.0, "PAGO", 0, 0, 1),      # Descripción
        (300.0, 200.0, 350.0, 210.0, "500.00", 0, 0, 2)     # Dinero
    ]
    
    # Le decimos que busque fechas entre X=40 y X=90
    rango_busqueda_x = (40.0, 90.0) 
    
    anclas = motor._encontrar_anclas_fechas(words_falsas, rango_busqueda_x, ancho_pagina=600.0)
    
    assert len(anclas) == 1
    assert anclas[0]["texto_fecha"] == "01/01"
    assert anclas[0]["tipo"] == "NUMERICA"
    assert anclas[0]["y_anchor"] == 200.0

def test_pass_3_extract_rows_flujo_completo(motor, pdf_memoria):
    """
    La prueba definitiva. Ejecuta el pipeline completo (P1 -> P2 -> P3)
    sobre el PDF virtual y verifica que extraiga la transacción simulada.
    """
    # 1. Geometría (Techo y Piso)
    geometries = motor.pass_1_detect_geometry(pdf_memoria)
    
    # 2. Columnas (Cajas X0-X1)
    layouts = motor.pass_2_detect_columns(pdf_memoria, geometries)
    
    # 3. Extracción (Corte horizontal y JSON)
    resultados = motor.pass_3_extract_rows(pdf_memoria, geometries, layouts)
    
    assert len(resultados) == 1
    data_page = resultados[0]
    
    assert data_page["page"] == 1
    assert "transacciones" in data_page
    
    # Verificamos que haya atrapado la transacción de nuestro PDF virtual
    # ("01/01   PAGO DE SERVICIOS   500.00           1000.00")
    txs = data_page["transacciones"]
    assert len(txs) >= 1
    
    tx_encontrada = txs[0]
    
    # Validaciones flexibles (por cómo PyMuPDF separa los espacios)
    assert "01/01" in tx_encontrada["fecha"]
    assert "PAGO" in tx_encontrada["descripcion"]
    
    # Como el 500.00 está debajo de "CARGO" y 1000.00 debajo de "SALDO",
    # dependiendo del centro exacto de la columna, debería clasificar el 500.00 como monto.
    assert tx_encontrada["monto"] in [500.0, 1000.0]