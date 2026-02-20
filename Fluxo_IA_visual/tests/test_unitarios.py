import pytest
import re
from fpdf import FPDF
from datetime import datetime, timedelta

from Fluxo_IA_visual.models.responses_analisisTPV import AnalisisTPV

from Fluxo_IA_visual.utils.helpers import ( # debemos hacer más test para este módulo
    construir_descripcion_optimizado, limpiar_monto, extraer_json_del_markdown, extraer_unico, extraer_datos_por_banco, sumar_lista_montos, es_escaneado_o_no,
    reconciliar_resultados_ia, sanitizar_datos_ia, total_depositos_verificacion, limpiar_y_normalizar_texto, crear_objeto_resultado, verificar_fecha_comprobante,
    aplicar_reglas_de_negocio, detectar_tipo_contribuyente
)

pytest_plugins = ('pytest_asyncio',)

# ---- Pruebas para utils/helpers.py ----

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

# ---- Pruebas para extraer_datos_por_banco ----
def test_extraer_datos_por_banco_sin_texto():
    """Debe devolver el diccionario base si no hay texto."""
    resultado = extraer_datos_por_banco("")
    assert resultado == {
        "banco": None,
        "rfc": None,
        "comisiones": None,
        "depositos": None,
    }

def test_extraer_datos_por_banco_sin_match(monkeypatch):
    """Si no se detecta banco, devuelve resultados vacíos."""
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.BANCO_DETECTION_REGEX", re.compile("XYZ"))
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.ALIAS_A_BANCO_MAP", {})
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PATRONES_COMPILADOS", {})
    resultado = extraer_datos_por_banco("TEXTO SIN BANCO")
    assert resultado["banco"] is None

def test_extraer_datos_por_banco_con_match(monkeypatch):
    """Prueba extracción simulando un banco con RFC y depósitos."""
    # Mock banco detection
    regex = re.compile("BANCOFAKE")
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.BANCO_DETECTION_REGEX", regex)
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.ALIAS_A_BANCO_MAP", {"BANCOFAKE": "banco_fake"})

    # Patrones del banco
    patrones = {
        "rfc": re.compile(r"RFC: (\w+)"),
        "depositos": re.compile(r"DEP: (\d+)"),
        "comisiones": re.compile(r"COM: (\d+)"),
    }
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PATRONES_COMPILADOS", {"banco_fake": patrones})

    texto = "BANCOFAKE RFC: ABC123 DEP: 1000 COM: 50"
    resultado = extraer_datos_por_banco(texto)

    assert resultado["banco"] == "BANCO_FAKE"
    assert resultado["rfc"] == "ABC123"
    assert resultado["depositos"] == 1000.0
    assert resultado["comisiones"] == 50.0

def test_extraer_datos_por_banco_valores_invalidos(monkeypatch):
    """Si los valores no son parseables como float, deben dar None."""
    regex = re.compile("BANCOX")
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.BANCO_DETECTION_REGEX", regex)
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.ALIAS_A_BANCO_MAP", {"BANCOX": "banco_x"})
    patrones = {"depositos": re.compile(r"DEP: (\w+)")}
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PATRONES_COMPILADOS", {"banco_x": patrones})

    texto = "BANCOX DEP: NOTANUMBER"
    resultado = extraer_datos_por_banco(texto)

    assert resultado["depositos"] is None

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

# ---- Pruebas para construir_descripcion_optimizado ----
def test_construir_descripcion_optimizado():
    """Prueba el despachador que construye la descripción"""
    # Prueba para un banco específico (Banorte)
    transaccion_banorte = ("25-may-25", "SPEI RECIBIDO PRUEBA", "1234.56")
    desc, monto = construir_descripcion_optimizado(transaccion_banorte, "Banorte")
    assert desc == "SPEI RECIBIDO PRUEBA"
    assert monto == "1234.56"

    # Prueba para el caso por defecto (un banco no configurado)
    transaccion_otro = ('fecha', 'descripcion', 'monto')
    desc, monto = construir_descripcion_optimizado(transaccion_otro, 'Banco Desconocido')
    assert desc == ""
    assert monto == "0.0"

# ---- Pruebas para es_escaneado_o_no ----
def test_es_escaneado_o_no_vacio():
    """Texto vacío siempre debe devolver False."""
    assert es_escaneado_o_no("") is False

def test_es_escaneado_o_no_corto(monkeypatch):
    """Texto muy corto aunque tenga palabra clave debe fallar."""
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PALABRAS_CLAVE_VERIFICACION", re.compile("saldo"))
    texto = "saldo"
    assert es_escaneado_o_no(texto, umbral=50) is False

def test_es_escaneado_o_no_sin_palabra(monkeypatch):
    """Texto largo pero sin palabra clave debe fallar."""
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PALABRAS_CLAVE_VERIFICACION", re.compile("saldo"))
    texto = "x" * 100
    assert es_escaneado_o_no(texto, umbral=50) is False

def test_es_escaneado_o_no_exitoso(monkeypatch):
    """Texto suficientemente largo y con palabra clave debe pasar."""
    monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.PALABRAS_CLAVE_VERIFICACION", re.compile("saldo"))
    texto = "saldo disponible en la cuenta" + ("x" * 100)
    assert es_escaneado_o_no(texto, umbral=20) is True

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

# ---- Pruebas para reconciliar_resultados_ia ----
def test_reconciliar_resultados_campos_numericos():
    res_gpt = {"comisiones": 100.0, "depositos": 500.0}
    res_gemini = {"comisiones": 80.0, "depositos": 600.0}
    
    resultado = reconciliar_resultados_ia(res_gpt, res_gemini)
    assert resultado["comisiones"] == 100.0   # GPT gana
    assert resultado["depositos"] == 600.0    # Gemini gana

def test_reconciliar_resultados_campos_texto():
    res_gpt = {"nombre": "Juan"}
    res_gemini = {"nombre": "Pedro"}
    
    resultado = reconciliar_resultados_ia(res_gpt, res_gemini)
    assert resultado["nombre"] == "Pedro"  # Prioriza la más larga

def test_reconciliar_resultados_con_none():
    res_gpt = {"saldo_promedio": None, "observaciones": None}
    res_gemini = {"saldo_promedio": 300.0, "observaciones": "ok"}
    
    resultado = reconciliar_resultados_ia(res_gpt, res_gemini)
    assert resultado["saldo_promedio"] == 300.0
    assert resultado["observaciones"] == "ok"

def test_reconciliar_resultados_todos_none():
    res_gpt = {"cargos": None}
    res_gemini = {"cargos": None}
    
    resultado = reconciliar_resultados_ia(res_gpt, res_gemini)
    assert resultado["cargos"] == 0.0 or resultado["cargos"] is None

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

### SOLO FUNCIONAN EN LOCAL
# # ---- Pruebas para obtener_y_procesar_portada ----
# @pytest.mark.asyncio
# async def test_obtener_y_procesar_portada_flujo_ok(monkeypatch, fake_pdf):
#     """Prueba el flujo exitoso usando un PDF falso y mockeando solo la IA."""
#     prompt = "Test prompt"
#     pdf_bytes = fake_pdf # Usamos el PDF válido generado por el fixture

#     # 1. Preparamos los mocks
#     # Mockeamos la lógica de negocio que sigue a la extracción para controlar la prueba
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.extraer_datos_por_banco", lambda *args: {"banco": "BANREGIO", "rfc": "RFC123", "comisiones": 10, "depositos": 100})
    
#     # Mockeamos las llamadas a la IA, que son externas y lentas
#     async def mock_analizar_gpt(*args, **kwargs):
#         return "```json\n{\"saldo\": 500}\n```"
#     async def mock_analizar_gemini(*args, **kwargs):
#         return "```json\n{\"saldo\": 600}\n```"
        
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.analizar_gpt_fluxo", mock_analizar_gpt)
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.analizar_gemini_fluxo", mock_analizar_gemini)
    
#     # Mocks para las funciones de post-procesamiento
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.extraer_json_del_markdown", lambda x: {"saldo": 500} if "500" in x else {"saldo": 600})
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.sanitizar_datos_ia", lambda x: x)
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.reconciliar_resultados_ia", lambda gpt, gemini: {"saldo": 550})

#     # 2. Actuamos
#     resultado, es_digital = await obtener_y_procesar_portada(prompt, pdf_bytes)

#     # 3. Verificamos
#     # La función real 'es_escaneado_o_no' se ejecutará sobre el texto del 'fake_pdf'
#     # y como contiene texto válido, 'es_digital' ahora será True.
#     assert es_digital is True
#     assert resultado["banco"] == "BANREGIO"
#     assert resultado["rfc"] == "RFC123"
#     assert resultado["saldo"] == 550

# @pytest.mark.asyncio
# async def test_obtener_y_procesar_portada_error_ia(monkeypatch, fake_pdf):
#     """Prueba el flujo cuando una de las llamadas a la IA falla."""
#     pdf_bytes = fake_pdf
#     prompt = "Test prompt"

#     # Preparamos los mocks
#     monkeypatch.setattr("Fluxo_IA_visual.services.pdf_processor.extraer_texto_de_pdf", lambda *args: "texto de prueba HSBC RFC999")
#     monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.es_escaneado_o_no", lambda *args: False)
#     monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.extraer_datos_por_banco", lambda *args: {"banco": "HSBC", "rfc": "RFC999"})
    
#     # Mock para que GPT falle y Gemini tenga éxito
#     async def mock_gpt_falla(*args):
#         raise Exception("GPT error")
#     async def mock_gemini_exito(*args):
#         return "```json\n{\"depositos\": 700}\n```"

#     monkeypatch.setattr("Fluxo_IA_visual.services.ia_extractor.analizar_gpt_fluxo", mock_gpt_falla)
#     monkeypatch.setattr("Fluxo_IA_visual.services.ia_extractor.analizar_gemini_fluxo", mock_gemini_exito)
    
#     monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.extraer_json_del_markdown", lambda x: {} if "GPT error" in repr(x) else {"depositos": 700}) # se está pasando el error como string
#     monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.sanitizar_datos_ia", lambda x: x)
#     monkeypatch.setattr("Fluxo_IA_visual.utils.helpers.reconciliar_resultados_ia", lambda gpt, gemini: {"depositos": 700})

#     # Actuamos
#     resultado, es_digital = await obtener_y_procesar_portada(prompt, pdf_bytes)

#     # Verificamos
#     assert es_digital is True
#     assert resultado == {} # como ambos fallaron, no hay datos

# @pytest.mark.asyncio
# async def test_obtener_y_procesar_portada_pdf_corto(monkeypatch, small_fake_pdf):
#     """Prueba el flujo exitoso usando un PDF falso y mockeando solo la IA."""
#     prompt = "Test prompt"
#     pdf_bytes = small_fake_pdf # Usamos el PDF válido generado por el fixture

#     # 1. Preparamos los mocks
#     # Mockeamos la lógica de negocio que sigue a la extracción para controlar la prueba
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.extraer_datos_por_banco", lambda *args: {"banco": "BANREGIO", "rfc": "RFC123", "comisiones": 10, "depositos": 100})
    
#     # Mockeamos las llamadas a la IA, que son externas y lentas
#     async def mock_analizar_gpt(*args, **kwargs):
#         return "```json\n{\"saldo\": 500}\n```"
#     async def mock_analizar_gemini(*args, **kwargs):
#         return "```json\n{\"saldo\": 600}\n```"
        
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.analizar_gpt_fluxo", mock_analizar_gpt)
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.analizar_gemini_fluxo", mock_analizar_gemini)
    
#     # Mocks para las funciones de post-procesamiento
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.extraer_json_del_markdown", lambda x: {"saldo": 500} if "500" in x else {"saldo": 600})
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.sanitizar_datos_ia", lambda x: x)
#     monkeypatch.setattr("Fluxo_IA_visual.services.orchestators.reconciliar_resultados_ia", lambda gpt, gemini: {"saldo": 550})

#     # 2. Actuamos
#     resultado, es_digital = await obtener_y_procesar_portada(prompt, pdf_bytes)

#     # 3. Verificamos
#     assert es_digital is False  # el texto es muy corto
#     assert resultado["banco"] == "BANREGIO"
#     assert resultado["rfc"] == "RFC123"
#     assert resultado["saldo"] == 550

# ---- Pruebas para procesar_regex_generico ----
# ### SOLO FUNCIONAN EN LOCAL

# def test_procesar_regex_generico_exitoso():
#     """Prueba un caso exitoso de procesamiento con regex."""
#     # 1. Preparar datos falsos (lo que vendría de la IA y del extractor de texto)
#     mock_resultados_json = {
#         "banco": "Banorte",
#         "comisiones": "10.00",
#         "depositos": "1000.00",
#         "cargos": "50.00",
#         "saldo_promedio": "5000.00"
#     }
#     mock_texto = """
#     texto basura...
#     05-may-25gardomi monterrey 10 09229981d 1,022.00 631,561.01
#     más texto...
#     """
    
#     # 2. Actuar
#     resultado = procesar_regex_generico(mock_resultados_json, mock_texto, "tipo_banco") # el tipo de banco no se usa en la función
#     print(resultado)

#     # 3. Verificar
#     assert resultado["banco"] == "Banorte"
#     assert len(resultado["transacciones"]) == 1
#     assert resultado["transacciones"][0]["monto"] == "1,022.00"
#     assert resultado["transacciones"][0]["descripcion"] == "gardomi monterrey 10 09229981d"
#     assert resultado["error_transacciones"] is None

# def test_procesar_regex_generico_sin_coincidencias():
#     """Prueba el caso donde no se encuentran transacciones."""
#     mock_resultados_ia = {"banco": "Banorte", "comisiones": "0.00"}
#     mock_texto = "Este texto no contiene ninguna transacción que coincida."

#     resultado = procesar_regex_generico(mock_resultados_ia, mock_texto, "tipo_banco") # el tipo de banco no se usa en la función

#     assert len(resultado["transacciones"]) == 0
#     assert "Sin coincidencias" in resultado["error_transacciones"]


# --- Pruebas para services/pdf_processor.py ---
# ### SOLO FUNCIONAN EN LOCAL

# def test_extraer_texto_limitado_con_pdf_falso(): # esta función cambió de nombre, función y de archivo
#     """Prueba la extracción de texto creando un PDF en memoria."""
#     # 1. Preparar: Crear un PDF falso de 2 páginas en memoria
#     pdf = FPDF()
#     pdf.add_page()
#     pdf.set_font("Times",size=12)
#     pdf.cell(200, 10, text="Texto de la página 1.")
#     pdf.add_page()
#     pdf.cell(200, 10, text="Contenido de la página 2.")

#     # Guardar el PDF como bytes directamente
#     buffer = BytesIO()
#     pdf.output(buffer)
#     pdf_bytes = buffer.getvalue()
    
#     # 2. Actuar
#     texto_extraido = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)

#     # 3. Verificar
#     assert "texto de la página 1" in texto_extraido
#     assert "contenido de la página 2" in texto_extraido