import pytest
import re
from Fluxo_IA_visual.core.motor_caratulas import MotorCaratulas

# ============================================================================
# FIXTURES (Configuraciones falsas para aislar el motor)
# ============================================================================
@pytest.fixture
def motor_test():
    """
    Crea una instancia limpia del MotorCaratulas con reglas muy simples
    para poder probar su lógica matemática y condicional sin fallos de regex.
    """
    triggers_config = {
        "inicio": ["detalle de la cuenta"],
        "fin": ["fin del estado de cuenta"]
    }
    palabras_clave_regex = re.compile(r"saldo|cuenta|clabe", re.IGNORECASE)
    alias_banco_map = {"banco patito": "BANCO_P"}
    banco_detection_regex = re.compile(r"banco patito", re.IGNORECASE)
    patrones_compilados = {
        "BANCO_P": {
            "rfc": re.compile(r"rfc:\s*([A-Z0-9]{12,13})", re.IGNORECASE),
            "depositos": re.compile(r"abonos\s*\$?([\d,]+\.\d{2})", re.IGNORECASE)
        }
    }
    
    return MotorCaratulas(
        triggers_config=triggers_config,
        palabras_clave_regex=palabras_clave_regex,
        alias_banco_map=alias_banco_map,
        banco_detection_regex=banco_detection_regex,
        patrones_compilados=patrones_compilados,
        debug_flags=None # Modo silencioso para tests
    )

# ============================================================================
# PRUEBAS: MÉTODOS BÁSICOS
# ============================================================================

def test_validar_documento_digital_texto_vacio(motor_test):
    """Si no hay texto, no es digital (es escaneado puro)."""
    assert motor_test.validar_documento_digital("") is False
    assert motor_test.validar_documento_digital(None) is False

def test_validar_documento_digital_texto_basura(motor_test):
    """Un texto largo pero sin palabras financieras clave, se rechaza."""
    texto_basura = "x" * 100 # Supera el umbral de 50 caracteres
    assert motor_test.validar_documento_digital(texto_basura) is False

def test_validar_documento_digital_valido(motor_test):
    """Texto largo y con palabras clave debe ser considerado digital."""
    texto_bueno = "Este documento contiene el saldo promedio del mes y otros datos."
    assert motor_test.validar_documento_digital(texto_bueno, umbral=20) is True

def test_extraer_unico(motor_test):
    """Prueba que el helper privado maneje listas, tuplas y vacíos correctamente."""
    # Lista de strings normales
    assert motor_test._extraer_unico(["100.00", "200.00"]) == "100.00"
    
    # Lista de tuplas (común cuando un regex tiene varios grupos de captura)
    assert motor_test._extraer_unico([("", "RFC123456XYZ", "")]) == "RFC123456XYZ"
    
    # Strings vacíos deben ser ignorados
    assert motor_test._extraer_unico(["", "   ", "DATO_REAL"]) == "DATO_REAL"
    
    # Listas vacías
    assert motor_test._extraer_unico([]) is None


# ============================================================================
# PRUEBAS: EXTRACCIÓN ESTÁTICA (REGEX)
# ============================================================================

def test_identificar_banco_y_datos_estaticos_sin_texto(motor_test):
    resultado = motor_test.identificar_banco_y_datos_estaticos("")
    assert resultado["banco"] is None

def test_identificar_banco_y_datos_estaticos_exito(motor_test):
    """Prueba que el motor lea el texto crudo y use los patrones compilados."""
    texto = "Bienvenido a banco patito. Su RFC: XYZ123456789. Total abonos $1,500.50"
    resultado = motor_test.identificar_banco_y_datos_estaticos(texto)
    
    assert resultado["banco"] == "BANCO_P"
    assert resultado["rfc"] == "XYZ123456789"
    assert resultado["depositos"] == 1500.50

# ============================================================================
# PRUEBAS: FILTRO DE CALIDAD (FALSOS POSITIVOS)
# ============================================================================

def test_es_cuenta_valida_rechaza_rfc_banco(motor_test):
    """Debe rechazar inmediatamente si el RFC pertenece a la lista negra (ej. BBVA)."""
    datos = {"rfc": "BBA830831LJ2", "clabe_interbancaria": "123456789012345678"}
    assert motor_test._es_cuenta_valida(datos, "texto cualquiera") is False

def test_es_cuenta_valida_acepta_clabe_perfecta(motor_test):
    """El Pase VIP: Si tiene CLABE de 18 dígitos, se acepta ignorando reglas de texto trampa."""
    datos = {"rfc": "CLIENTE12345", "clabe_interbancaria": " 012345678901234567 "} # Con espacios extra
    texto_trampa = "estado de cuenta de inversiones" # Esto rechazaría si no tuviera CLABE
    assert motor_test._es_cuenta_valida(datos, texto_trampa) is True

def test_es_cuenta_valida_rechaza_inversiones_sin_clabe(motor_test):
    """Si el texto dice inversiones y NO tiene CLABE, es sub-cuenta basura."""
    datos = {"rfc": "CLIENTE12345", "clabe_interbancaria": ""}
    texto = "Este es un estado de cuenta de inversiones del mes de Diciembre."
    assert motor_test._es_cuenta_valida(datos, texto) is False

def test_es_cuenta_valida_rechaza_sin_datos_minimos(motor_test):
    """Si no tiene CLABE y su RFC es muy corto o nulo, es basura y se descarta."""
    datos_sin_nada = {"rfc": "CORTO", "clabe_interbancaria": None}
    assert motor_test._es_cuenta_valida(datos_sin_nada, "texto normal sin trampas") is False

# ============================================================================
# PRUEBAS: RECONCILIACIÓN INTELIGENTE (TRIANGULACIÓN)
# ============================================================================

def test_reconciliar_extracciones_acuerdo_total(motor_test):
    """Si Qwen y GPT están de acuerdo en un monto, se usa ese valor indiscutiblemente."""
    datos_regex = {}
    datos_qwen = {"depositos": 1000.0, "comisiones": 50.0}
    datos_gpt = {"depositos": 1000.0, "comisiones": 50.0}
    
    res = motor_test.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)
    assert res["depositos"] == 1000.0
    assert res["comisiones"] == 50.0

def test_reconciliar_extracciones_desempate_con_regex(motor_test):
    """Si Qwen y GPT difieren, el Regex (Verdad Base) actúa como juez de desempate."""
    datos_regex = {"depositos": 2500.0}
    datos_qwen = {"depositos": 9999.0}  # Qwen alucinó un número
    datos_gpt = {"depositos": 2500.0}   # GPT coincide con el Regex
    
    res = motor_test.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)
    assert res["depositos"] == 2500.0   # Gana GPT por tener el respaldo del Regex

def test_reconciliar_extracciones_fallback_gpt(motor_test):
    """Si hay discrepancia total y no hay Regex, prefiere el número de GPT por seguridad (suele leer mejor tablas)."""
    datos_regex = {}
    datos_qwen = {"depositos": 100.0}
    datos_gpt = {"depositos": 500.0}
    
    res = motor_test.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)
    assert res["depositos"] == 500.0

def test_reconciliar_extracciones_prioridad_rfc_regex(motor_test):
    """Para datos duros como el RFC, el Regex tiene autoridad absoluta si lo encontró."""
    datos_regex = {"rfc": "REGEX1234567"}
    datos_qwen = {"rfc": "QWEN12345678"}
    datos_gpt = {"rfc": "GPTX12345678"}
    
    res = motor_test.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)
    assert res["rfc"] == "REGEX1234567"
    
def test_reconciliar_extracciones_clabe_larga(motor_test):
    """Para la CLABE, gana el modelo que devuelva exactamente los 18 dígitos."""
    datos_regex = {}
    datos_qwen = {"clabe_interbancaria": "123456"} # Qwen cortó el texto
    datos_gpt = {"clabe_interbancaria": "012345678901234567"} # GPT perfecto
    
    res = motor_test.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)
    assert res["clabe_interbancaria"] == "012345678901234567"