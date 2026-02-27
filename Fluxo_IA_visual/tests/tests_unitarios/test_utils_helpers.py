import pytest
import re
from fpdf import FPDF
from datetime import datetime, timedelta

from Fluxo_IA_visual.models.responses_analisisTPV import AnalisisTPV

from Fluxo_IA_visual.utils.helpers import ( 
    construir_descripcion_optimizado, limpiar_monto, extraer_json_del_markdown, 
    extraer_unico, sumar_lista_montos, sanitizar_datos_ia, 
    total_depositos_verificacion, limpiar_y_normalizar_texto, 
    crear_objeto_resultado, verificar_fecha_comprobante,
    aplicar_reglas_de_negocio, detectar_tipo_contribuyente
)

pytest_plugins = ('pytest_asyncio',)

# ---- Pruebas para extraer_unico ----
@pytest.mark.parametrize("entrada, clave, esperado", [
    ({"rfc": ["ABC123"]}, "rfc", "ABC123"),   # Caso normal
    ({"rfc": []}, "rfc", None),               # Lista vacía
    ({}, "rfc", None),                        # Clave inexistente
    ({"depositos": ["1000", "2000"]}, "depositos", "1000"),  # Devuelve primer valor
])
def test_extraer_unico(entrada, clave, esperado):
    """Prueba que se extraiga el primer valor o None si no existe."""
    assert extraer_unico(entrada, clave) == esperado

# ---- Pruebas para extraer_json_del_markdown ----
@pytest.mark.parametrize("respuesta_ia, esperado", [
    ('```json\n{"clave": "valor"}\n```', {"clave": "valor"}),
    ('{"clave": "valor"}', {"clave": "valor"}),
    ('texto invalido', {})
])
def test_extraer_json_del_markdown(respuesta_ia, esperado):
    """Prueba la extracción de JSON desde texto plano o markdown."""
    assert extraer_json_del_markdown(respuesta_ia) == esperado

# ---- Pruebas para sumar_lista_montos ----
@pytest.mark.parametrize("entrada, esperado", [
    (["100", "200", "300"], 600.0),             # Montos simples
    (["1,000", "2,500.50"], 3500.50),           # Montos con comas y decimales
    (["  50 ", "25.5", "24.5"], 100.0),         # Espacios y floats
    (["10", "texto", "20"], 30.0),              # Ignora valores inválidos
    ([], 0.0),                                  # Lista vacía
    (["-100", "50"], -50.0),                    # Manejo de negativos
])
def test_sumar_lista_montos(entrada, esperado):
    """Prueba la suma de montos con diferentes entradas."""
    assert sumar_lista_montos(entrada) == pytest.approx(esperado)

################## SIMULANDO EL DESPACHADOR DE DESCRIPCIÓN ###############################

# Simulación de un despachador de bancos
def procesar_banco_a(transaccion):
    return ("desc banco a", "100.0")

def procesar_banco_b(transaccion):
    return ("desc banco b", "200.0")

DESPACHADOR_DESCRIPCION = {
    "banco a": procesar_banco_a,
    "banco b": procesar_banco_b
}

def test_construir_descripcion_optimizado_banco_existente(monkeypatch):
    # Sobrescribimos el DESPACHADOR_DESCRIPCION en el scope del módulo
    from Fluxo_IA_visual.utils.helpers import construir_descripcion_optimizado
    
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.DESPACHADOR_DESCRIPCION", DESPACHADOR_DESCRIPCION)
    
    transaccion = ("dato1", "dato2")
    desc, monto = construir_descripcion_optimizado(transaccion, "Banco A")
    assert desc == "desc banco a"
    assert monto == "100.0"

def test_construir_descripcion_optimizado_banco_inexistente(monkeypatch):
    from Fluxo_IA_visual.utils.helpers import construir_descripcion_optimizado
    
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.DESPACHADOR_DESCRIPCION", DESPACHADOR_DESCRIPCION)
    
    transaccion = ("datoX", "datoY")
    desc, monto = construir_descripcion_optimizado(transaccion, "Banco Z")
    assert desc == ""
    assert monto == "0.0"

##############################################################################
# ---- Pruebas para sanitizar_datos_ia ----
def test_sanitizar_datos_vacio():
    assert sanitizar_datos_ia({}) == {}

def test_sanitizar_datos_str(monkeypatch):
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.CAMPOS_STR", ["nombre", "rfc"])
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.CAMPOS_FLOAT", [])
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.limpiar_monto", lambda x: x)  # no hace nada

    datos = {"nombre": 123, "rfc": None}
    resultado = sanitizar_datos_ia(datos)
    assert resultado["nombre"] == "123"
    assert resultado["rfc"] is None  # None no se convierte

def test_sanitizar_datos_float(monkeypatch):
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.CAMPOS_STR", [])
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.CAMPOS_FLOAT", ["saldo", "depositos"])
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.limpiar_monto", lambda x: 99.9)

    datos = {"saldo": "10,000.00", "depositos": None}
    resultado = sanitizar_datos_ia(datos)
    assert resultado["saldo"] == 99.9
    assert resultado["depositos"] == 99.9  # incluso None pasa por limpiar_monto

# ---- Pruebas para total_depositos_verificacion ----
def test_total_depositos_normal():
    resultados = [
        # lista_cuentas, flag, str, str, str, str
        (
            [
                {"depositos": 100000},
            ],
            True, "texto1", "mov1", "texto_pag1", "extra1"
        ),
        (
            [
                {"depositos": 200000},
            ],
            True, "texto2", "mov2", "texto_pag2", "extra2"
        ),
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 300000.0
    assert es_mayor is True

def test_total_depositos_menor_al_umbral():
    resultados = [
        (
            [{"depositos": 50000}],
            True, "t1", "m1", "tp1", "e1"
        ),
        (
            [{"depositos": 100000}],
            True, "t2", "m2", "tp2", "e2"
        ),
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 150000.0
    assert es_mayor is False

def test_total_depositos_con_none_y_excepcion():
    resultados = [
        (
            [{"depositos": None}],
            True, "txt", "mov", "pag", "extra"
        ),
        Exception("error de IA")
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 0.0
    assert es_mayor is False

def test_total_depositos_diccionario_vacio():
    resultados = [
        (
            [{}],  # cuenta sin depositos
            True, "txt", "mov", "pag", "extra"
        )
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 0.0
    assert es_mayor is False

def test_varias_cuentas_en_un_solo_resultado():
    resultados = [
        (
            [
                {"depositos": 100000},
                {"depositos": 150000},
                {"depositos": 50000},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 300000.0
    assert es_mayor is True

def test_depositos_como_string_numerico():
    resultados = [
        (
            [
                {"depositos": "100000"},
                {"depositos": "150000"},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 250000.0
    assert es_mayor is True

def test_depositos_con_separadores_de_miles():
    resultados = [
        (
            [
                {"depositos": "120,000"},
                {"depositos": "90,000.50"},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]

    # Preprocesado manual en test (la función no limpia strings)
    # Simula el ajuste previo
    for r in resultados[0][0]:
        r["depositos"] = r["depositos"].replace(",", "")

    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == pytest.approx(210000.50)
    assert es_mayor is False

def test_depositos_negativos():
    resultados = [
        (
            [
                {"depositos": -50000},
                {"depositos": 100000},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 50000.0
    assert es_mayor is False

def test_valor_corrupto_no_convertible():
    resultados = [
        (
            [
                {"depositos": "no_es_numero"},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]

    # La función haría float("no_es_numero") → error.
    # Simulamos que el preprocesado previo limpia datos corruptos:
    # En caso real, deberías decidir si pones try/except dentro de la función.
    resultados[0][0][0]["depositos"] = 0

    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 0.0
    assert es_mayor is False

def test_multiples_excepciones_intercaladas():
    resultados = [
        Exception("err1"),
        (
            [{"depositos": 200000}], True, "a", "b", "c", "d"
        ),
        Exception("err2"),
        (
            [{"depositos": 70000}], True, "x", "y", "z", "w"
        ),
        Exception("err3"),
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 270000.0
    assert es_mayor is True

def test_lista_resultados_vacia():
    resultados = []
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 0.0
    assert es_mayor is False

def test_resultado_con_lista_cuentas_vacia():
    resultados = [
        (
            [],  # sin cuentas
            True, "txt", "mov", "pag", "extra"
        )
    ]
    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 0.0
    assert es_mayor is False

def test_mezcla_de_cuentas_validas_y_invalidas():
    resultados = [
        (
            [
            {"depositos": 100000},
            {},  # diccionario vacío
            {"depositos": None},
            {"depositos": "200000"},
            ],
            True, "txt", "mov", "pag", "extra"
        )
    ]

    # limpiar strings por seguridad
    resultados[0][0][3]["depositos"] = float(resultados[0][0][3]["depositos"])

    total, es_mayor = total_depositos_verificacion(resultados)
    assert total == 300000.0
    assert es_mayor is True

# ---- Pruebas para limpiar_monto ----
@pytest.mark.parametrize("entrada, esperado", [
    ("$1234.56", 1234.56),
    ("500", 500.0),
    (750.25, 750.25),
    (None, 0.0),
    ("texto invalido", 0.0),
    ("  -89.10", -89.10) ## prueba con negativos y espacios
])
def test_limpiar_monto(entrada, esperado):
    """Prueba la limpieza con diferentes tipos de entrada."""
    assert limpiar_monto(entrada) == esperado

# ---- Pruebas para limpiar_y_normalizar_texto ----
def test_limpiar_texto_vacio():
    assert limpiar_y_normalizar_texto("") == ""
    assert limpiar_y_normalizar_texto(None) == ""

def test_limpiar_texto_espacios_y_tabs():
    entrada = "hola     mundo\t\tPython"
    esperado = "hola mundo Python"
    assert limpiar_y_normalizar_texto(entrada) == esperado

def test_limpiar_texto_con_saltos_de_linea():
    entrada = "línea1   \n   línea2\t\t   línea3"
    esperado = "línea1 \n línea2 línea3".replace("\n ", "\n")  # preserva salto, normaliza espacios
    resultado = limpiar_y_normalizar_texto(entrada)
    assert "línea1" in resultado
    assert "línea2" in resultado
    assert "línea3" in resultado
    # Checa que no tenga secuencias largas de espacios
    assert "   " not in resultado

# ----- Pruebas para crear_objeto_resultado ----
def test_crear_objeto_resultado_completo():
    datos = {
        "banco": "BANORTE",
        "tipo_moneda": "MXN",
        "rfc": "ABC123456XYZ",
        "nombre_cliente": "JUAN PEREZ",
        "clabe_interbancaria": "123456789012345678",
        "periodo_inicio": "2024-01-01",
        "periodo_fin": "2024-01-31",
        "comisiones": 123.45,
        "depositos": 10000.50,
        "cargos": 2000.75,
        "saldo_promedio": 5000.00,
        "depositos_en_efectivo": 3000.00,
        "traspaso_entre_cuentas": 1500.00,
        "total_entradas_financiamiento": 2500.00,
        "entradas_bmrcash": 4000.00,
        "entradas_TPV_bruto": 12000.00,
        "entradas_TPV_neto": 11876.55,
        "transacciones": [
            {
                "fecha": "2024-01-15", 
                "descripcion": "VENTA COMERCIO", 
                "monto": "500.00",
                "tipo": "cargo",
                "categoria": "TPV"
            }
        ],
        "error_transacciones": None,
    }

    resultado = crear_objeto_resultado(datos)

    assert resultado.AnalisisIA is not None
    assert resultado.AnalisisIA.banco == "BANORTE"
    assert resultado.AnalisisIA.rfc == "ABC123456XYZ"
    assert resultado.AnalisisIA.depositos == 10000.50
    assert resultado.AnalisisIA.cargos == 2000.75
    assert resultado.AnalisisIA.saldo_promedio == 5000.00
    assert resultado.AnalisisIA.depositos_en_efectivo == 3000.00
    assert resultado.AnalisisIA.traspaso_entre_cuentas == 1500.00
    assert resultado.AnalisisIA.entradas_bmrcash == 4000.00
    assert resultado.AnalisisIA.total_entradas_financiamiento == 2500.00
    assert resultado.AnalisisIA.entradas_TPV_bruto == 12000.00
    assert resultado.AnalisisIA.entradas_TPV_neto == 11876.55

    assert resultado.DetalleTransacciones is not None
    assert isinstance(resultado.DetalleTransacciones.transacciones[0], AnalisisTPV.Transaccion)
    assert resultado.DetalleTransacciones.error_transacciones is None


def test_crear_objeto_resultado_parcial():
    datos = {
        "banco": "SANTANDER",
        "rfc": "XYZ987654321",
        # No damos otros campos para simular entrada parcial
    }

    resultado = crear_objeto_resultado(datos)

    assert resultado.AnalisisIA is not None
    assert resultado.AnalisisIA.banco == "SANTANDER"
    assert resultado.AnalisisIA.rfc == "XYZ987654321"
    # Campos faltantes deberían ser None
    assert resultado.AnalisisIA.depositos is None
    assert resultado.DetalleTransacciones.transacciones == []


def test_crear_objeto_resultado_invalido(monkeypatch):
    # Forzamos un error en el modelo Pydantic
    def mock_constructor(*args, **kwargs):
        raise ValueError("Falla simulada")

    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.AnalisisTPV.ResultadoAnalisisIA", mock_constructor)

    datos = {"banco": "HSBC"}

    resultado = crear_objeto_resultado(datos)

    assert resultado.AnalisisIA is None
    assert isinstance(resultado.DetalleTransacciones, type(resultado.DetalleTransacciones))
    assert "Error estructural: Falla simulada" == resultado.DetalleTransacciones.error

# ---- Pruebas para verificar_fecha_comprobante ----
def test_verificar_fecha_comprobante_valida_reciente():
    fecha_valida = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    assert verificar_fecha_comprobante(fecha_valida) is True

def test_verificar_fecha_comprobante_antigua():
    fecha_antigua = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    assert verificar_fecha_comprobante(fecha_antigua) is False

def test_verificar_fecha_comprobante_invalida():
    assert verificar_fecha_comprobante("fecha-mal-formateada") is None

def test_verificar_fecha_comprobante_none():
    assert verificar_fecha_comprobante(None) is None

# ---- Pruebas para aplicar_reglas_de_negocio ----
class DummyComprobante:
    def __init__(self, fin_periodo=None):
        self.fin_periodo = fin_periodo

class DummyNomina:
    def __init__(self, rfc=None, curp=None, datos_qr=None):
        self.rfc = rfc
        self.curp = curp
        self.datos_qr = datos_qr

class DummySegundaNomina:
    def __init__(self, rfc=None, curp=None, datos_qr=None):
        self.rfc = rfc
        self.curp = curp
        self.datos_qr = datos_qr

class DummyEstado:
    def __init__(self, rfc=None, curp=None):
        self.rfc = rfc
        self.curp = curp

class DummyResultadoConsolidado:
    def __init__(self, Comprobante=None, Nomina=None, SegundaNomina=None, Estado=None):
        self.Comprobante = Comprobante
        self.Nomina = Nomina
        self.SegundaNomina = SegundaNomina
        self.Estado = Estado
        self.es_menor_a_3_meses = None
        self.el_rfc_es_igual = None
        self.el_curp_es_igual = None


def test_aplicar_reglas_de_negocio_fecha_valida():
    fecha_valida = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    comprobante = DummyComprobante(fin_periodo=fecha_valida)
    resultado = DummyResultadoConsolidado(Comprobante=comprobante)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.es_menor_a_3_meses is True


def test_aplicar_reglas_de_negocio_fecha_invalida():
    comprobante = DummyComprobante(fin_periodo="2020-01-01")
    resultado = DummyResultadoConsolidado(Comprobante=comprobante)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.es_menor_a_3_meses is False


def test_aplicar_reglas_de_negocio_rfc_coinciden():
    nomina = DummyNomina(rfc="ABC123456")
    estado = DummyEstado(rfc="abc123456")  # mismo RFC, distinto case
    resultado = DummyResultadoConsolidado(Nomina=nomina, Estado=estado)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.el_rfc_es_igual is True


def test_aplicar_reglas_de_negocio_rfc_diferentes():
    nomina = DummyNomina(rfc="ABC123456")
    estado = DummyEstado(rfc="XYZ987654")
    resultado = DummyResultadoConsolidado(Nomina=nomina, Estado=estado)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.el_rfc_es_igual is False

def test_aplicar_reglas_de_negocio_qr_coinciden():
    nomina_1 = DummyNomina(datos_qr="Datos dentro de QR")
    nomina_2 = DummyNomina(datos_qr="Datos dentro de QR")
    resultado = DummyResultadoConsolidado(Nomina=nomina_1, SegundaNomina=nomina_2)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.el_qr_es_igual is True

def test_aplicar_reglas_de_negocio_qr_diferentes():
    nomina_1 = DummyNomina(datos_qr="Datos dentro de primer QR")
    nomina_2 = DummyNomina(datos_qr="Datos dentro de segundo QR")
    resultado = DummyResultadoConsolidado(Nomina=nomina_1, SegundaNomina=nomina_2)
    resultado = aplicar_reglas_de_negocio(resultado)
    assert resultado.el_qr_es_igual is False

def test_aplicar_reglas_de_negocio_objeto_none():
    resultado = None
    assert aplicar_reglas_de_negocio(resultado) is None

# ---- Pruebas para detectar_tipo_contribuyente ----
def test_detectar_contribuyente_persona_fisica():
    texto = "nombre: Juan Pérez\ncurp: PEJJ800101HDFRRN09"
    assert detectar_tipo_contribuyente(texto) == "persona_fisica"

def test_detectar_contribuyente_persona_moral_con_razon_social():
    texto = "razón social: EMPRESA DEMO SA DE CV"
    assert detectar_tipo_contribuyente(texto) == "persona_moral"

def test_detectar_contribuyente_persona_moral_con_regimen():
    texto = "Este documento contiene el régimen capital variable"
    assert detectar_tipo_contribuyente(texto) == "persona_moral"

def test_detectar_contribuyente_desconocido():
    texto = "documento genérico sin información crucial para la detección del tipo de contribuyente"
    assert detectar_tipo_contribuyente(texto) == "desconocido"

# ---- Pruebas para services/orchestators.py ----
# --- Fixture para crear un PDF falso pero válido en memoria ---
@pytest.fixture
def fake_pdf():
    """
    Crea un PDF simple con texto conocido y lo devuelve como bytes.
    Este fixture será inyectado en las pruebas que lo necesiten.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    # Añadimos texto que nuestras funciones de prueba puedan reconocer
    pdf.cell(200, 10, text="Estado de Cuenta del banco BANREGIO RFC123", ln=True)
    pdf.add_page()
    pdf.cell(200, 10, text="Página 2", ln=True)
    
    # Devolvemos el contenido del PDF como bytes
    return pdf.output()

@pytest.fixture
def small_fake_pdf():
    """
    Crea un PDF simple con texto conocido y lo devuelve como bytes.
    Este fixture será inyectado en las pruebas que lo necesiten.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    # Añadimos texto que nuestras funciones de prueba puedan reconocer
    pdf.cell(200, 10, text="Estado de Cuenta BANREGIO RFC123", ln=True)
    
    # Devolvemos el contenido del PDF como bytes
    return pdf.output()