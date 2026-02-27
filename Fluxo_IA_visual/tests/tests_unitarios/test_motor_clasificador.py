import pytest
from Fluxo_IA_visual.core.motor_clasificador import MotorClasificador

# ============================================================================
# MOCKS Y FIXTURES
# ============================================================================

class TransaccionMock:
    """Objeto falso para simular AnalisisTPV.Transaccion sin depender de Pydantic."""
    def __init__(self, descripcion, monto, tipo, categoria="GENERAL"):
        self.descripcion = descripcion
        self.monto = monto
        self.tipo = tipo
        self.categoria = categoria

@pytest.fixture
def motor_clasificador_test():
    """Motor configurado con diccionarios pequeños para pruebas controladas."""
    diccionarios = {
        'excluidas': ['comision', 'manejo de cuenta'],
        'efectivo': ['deposito en efectivo', 'dep. efectivo'],
        'traspaso': ['traspaso entre cuentas', 'spei enviado'],
        # Dejamos los demás vacíos para simplificar
        'financiamiento': [], 'bmrcash': [], 'moratorio': []
    }
    return MotorClasificador(diccionarios_palabras=diccionarios, debug_flags=None)

# ============================================================================
# PRUEBAS: CAPA 1 (PRE-CLASIFICACIÓN ESTÁTICA / EMBUDO)
# ============================================================================

def test_pre_clasificar_descarta_cargos(motor_clasificador_test):
    """Cualquier retiro o cargo debe ir directo a la cubeta 'resueltas' como GENERAL."""
    tx_cargo = TransaccionMock("PAGO DE LUZ", "500", "cargo")
    tx_retiro = TransaccionMock("RETIRO CAJERO", "100", "retiro")
    
    resueltas, pendientes = motor_clasificador_test._pre_clasificar_transacciones([tx_cargo, tx_retiro])
    
    assert len(resueltas) == 2
    assert len(pendientes) == 0
    # Verificamos que se les asignó la categoría correctamente
    assert resueltas[0][1].categoria == "GENERAL"
    assert resueltas[1][1].categoria == "GENERAL"

def test_pre_clasificar_resuelve_palabras_clave(motor_clasificador_test):
    """Abonos con palabras clave exactas (efectivo, traspaso) no deben ir a la IA."""
    tx_efectivo = TransaccionMock("DEPOSITO EN EFECTIVO SUC 123", "1000", "abono")
    tx_traspaso = TransaccionMock("TRASPASO ENTRE CUENTAS", "2000", "deposito")
    
    resueltas, pendientes = motor_clasificador_test._pre_clasificar_transacciones([tx_efectivo, tx_traspaso])
    
    assert len(resueltas) == 2
    assert len(pendientes) == 0
    assert resueltas[0][1].categoria == "EFECTIVO"
    assert resueltas[1][1].categoria == "TRASPASO"

def test_pre_clasificar_envia_ambiguos_a_ia(motor_clasificador_test):
    """Abonos que no cruzan con ninguna regla estática deben enviarse a la cubeta de la IA."""
    tx_rara = TransaccionMock("PAGO NETPAY SAPI", "5000", "abono") # Podría ser TPV
    tx_efectivo = TransaccionMock("DEP. EFECTIVO", "100", "abono") # Esta sí la sabemos
    
    resueltas, pendientes = motor_clasificador_test._pre_clasificar_transacciones([tx_rara, tx_efectivo])
    
    assert len(resueltas) == 1
    assert len(pendientes) == 1
    
    # La pendiente debe ser la tx_rara y debe conservar su índice original (0)
    assert pendientes[0][0] == 0
    assert pendientes[0][1].descripcion == "PAGO NETPAY SAPI"

# ============================================================================
# PRUEBAS: CAPA 4 (SUMATORIAS Y MATEMÁTICAS)
# ============================================================================

def test_calcular_totales_suma_correcta(motor_clasificador_test):
    """Prueba que los abonos se sumen en sus categorías y los cargos se ignoren."""
    txs = [
        TransaccionMock("Venta 1", "1,000.50", "abono", "TPV"),
        TransaccionMock("Venta 2", "500.00", "abono", "TERMINAL DE VENTA"), # Alias válido de TPV
        TransaccionMock("Depósito en sucursal", "200.00", "deposito", "EFECTIVO"),
        TransaccionMock("Comisión", "50.00", "cargo", "GENERAL"), # Es cargo, no suma a los ingresos
        TransaccionMock("Error OCR", "MontoInvalido", "abono", "TPV") # Monto corrupto, asume 0
    ]
    
    totales = motor_clasificador_test._calcular_totales(txs)
    
    # 1000.50 + 500.00
    assert totales["TPV"] == 1500.50 
    assert totales["EFECTIVO"] == 200.00
    # Depósitos totales debe ser la suma de todos los abonos (1500.50 + 200)
    assert totales["DEPOSITOS"] == 1700.50

# ============================================================================
# PRUEBAS: ORQUESTACIÓN COMPLETA (MOCK DE IA ASÍNCRONA)
# ============================================================================

@pytest.mark.asyncio
async def test_clasificar_y_sumar_transacciones_flujo_completo(motor_clasificador_test):
    """
    Prueba el embudo completo. Simula una función de IA asíncrona para no 
    llamar a la API real y verifica que las categorías se asignen a los objetos correctos.
    """
    # 1. Preparamos 3 transacciones de prueba
    txs = [
        TransaccionMock("CARGO LUZ", "100", "cargo"),        # Índice 0: Resuelto por Python
        TransaccionMock("DEP. EFECTIVO", "200", "abono"),    # Índice 1: Resuelto por Python
        TransaccionMock("PAGO RARO NETPAY", "500", "abono")  # Índice 2: Va para la IA
    ]

    # 2. Creamos una función IA falsa (Mock)
    async def mock_ia(banco, lote):
        # El lote solo debería traer el ID 2
        assert len(lote) == 1
        assert lote[0]["id"] == 2
        # Respondemos simulando a GPT
        return {"2": "TPV"}

    # 3. Disparamos el orquestador inyectando nuestra IA falsa
    totales = await motor_clasificador_test.clasificar_y_sumar_transacciones(
        transacciones=txs,
        banco="bbva",
        funcion_ia_clasificadora=mock_ia,
        batch_size=100
    )

    # 4. Verificamos que las piezas del rompecabezas encajaron
    assert txs[0].categoria == "GENERAL"  # Descartada por cargo
    assert txs[1].categoria == "EFECTIVO" # Capturada por diccionario
    assert txs[2].categoria == "TPV"      # Marcada exitosamente por la IA simulada
    
    # Verificamos los totales finales
    assert totales["TPV"] == 500.0
    assert totales["EFECTIVO"] == 200.0
    assert totales["DEPOSITOS"] == 700.0