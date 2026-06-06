import pytest
from unittest.mock import patch
from Fluxo_IA_visual.core.motor_clasificador import MotorClasificador
from Fluxo_IA_visual.utils.tags_y_pesos_fluxo import CategoriaTag

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
        self.razon_clasificacion = ""

@pytest.fixture
def motor_clasificador_test():
    """Motor configurado con diccionarios pequeños para pruebas controladas."""
    
    # Creamos un ecosistema falso de Tags y Pesos solo para el Test
    config_mock = {
        CategoriaTag.EXCLUIDA: {"peso": 9999, "palabras": ['comision', 'manejo de cuenta']},
        CategoriaTag.EFECTIVO: {"peso": 30, "palabras": ['deposito en efectivo', 'dep. efectivo']},
        CategoriaTag.TRASPASO: {"peso": 40, "palabras": ['traspaso entre cuentas', 'spei enviado']},
        CategoriaTag.TPV: {"peso": 80, "palabras": []}, # Lo dejamos vacío porque no se evalúa estáticamente en estos tests
        CategoriaTag.FINANCIAMIENTO: {"peso": 50, "palabras": []},
        CategoriaTag.PAGO_FINANCIAMIENTO: {"peso": 50, "palabras": []},
        CategoriaTag.BMRCASH: {"peso": 30, "palabras": []},
        CategoriaTag.MORATORIOS: {"peso": 20, "palabras": []},
        CategoriaTag.IVA: {"peso": 1000, "palabras": ["iva"]},
        CategoriaTag.COMISION_CR: {"peso": 100, "palabras": []},
        CategoriaTag.COMISION_DB: {"peso": 100, "palabras": []},
        CategoriaTag.COMISION_AMEX: {"peso": 100, "palabras": []},
        CategoriaTag.COMISION_MIXTA: {"peso": 90, "palabras": []}
    }
    
    # Parcheamos la constante dentro del módulo donde vive el MotorClasificador
    with patch('Fluxo_IA_visual.core.motor_clasificador.CONFIGURACION_TAGS', config_mock):
        yield MotorClasificador(debug_flags=None)

# ============================================================================
# PRUEBAS: CAPA 1 (PRE-CLASIFICACIÓN ESTÁTICA / EMBUDO)
# ============================================================================

def test_pre_clasificar_envia_cargos_generales_a_ia(motor_clasificador_test):
    """Los cargos comunes que no hacen match con reglas estáticas deben enviarse a la IA."""
    tx_cargo = TransaccionMock("PAGO DE LUZ", "500", "cargo")
    tx_retiro = TransaccionMock("RETIRO CAJERO", "100", "retiro")
    
    resueltas, pendientes = motor_clasificador_test._pre_clasificar_transacciones([tx_cargo, tx_retiro])
    
    # Verificamos que ahora se van a la cubeta de la IA
    assert len(resueltas) == 0
    assert len(pendientes) == 2

def test_pre_clasificar_resuelve_palabras_clave(motor_clasificador_test):
    """Abonos con palabras clave exactas (efectivo, traspaso) no deben ir a la IA."""
    tx_efectivo = TransaccionMock("DEPOSITO EN EFECTIVO SUC 123", "1000", "abono")
    tx_traspaso = TransaccionMock("TRASPASO ENTRE CUENTAS", "2000", "deposito")
    
    resueltas, pendientes = motor_clasificador_test._pre_clasificar_transacciones([tx_efectivo, tx_traspaso])
    
    assert len(resueltas) == 2
    assert len(pendientes) == 0
    assert resueltas[0][1].categoria == "EFECTIVO"
    assert resueltas[1][1].categoria == "TRASPASO_ABONO"

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
            TransaccionMock("Venta 1", "1000.50", "abono", "TPV"),
            TransaccionMock("Venta 2", "500.00", "abono", "TPV"), 
            TransaccionMock("Depósito en sucursal", "200.00", "deposito", "EFECTIVO"),
            TransaccionMock("Comisión", "50.00", "cargo", "GENERAL"), # Es cargo, no suma a los ingresos
            TransaccionMock("Error OCR", "MontoInvalido", "abono", "TPV") # Monto corrupto, asume 0
        ]

        totales = motor_clasificador_test._calcular_totales(txs)

        # 1000.50 + 500.00 + 0.00
        assert totales["TPV"] == 1500.50
        assert totales["EFECTIVO"] == 200.00
        assert totales["TRASPASO_ABONO"] == 0.0
        # Verificamos que la comisión (cargo) no haya sumado a ingresos
        assert totales["COMISION_CR"] == 0.0

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
        TransaccionMock("CARGO LUZ", "100", "cargo"),        # Índice 0: AHORA VA PARA LA IA
        TransaccionMock("DEP. EFECTIVO", "200", "abono"),    # Índice 1: Resuelto por Python
        TransaccionMock("PAGO RARO NETPAY", "500", "abono")  # Índice 2: Va para la IA
    ]

    # 2. Creamos una función IA falsa (Mock)
    async def mock_ia(banco, lote):
        # El lote ahora trae el ID 0 y el ID 2
        assert len(lote) == 2
        ids_recibidos = [item["id"] for item in lote]
        assert 0 in ids_recibidos
        assert 2 in ids_recibidos
        
        # Respondemos simulando a GPT para ambas transacciones
        return {"0": "GENERAL", "2": "TPV"}

    # 3. Disparamos el orquestador inyectando nuestra IA falsa
    totales = await motor_clasificador_test.clasificar_y_sumar_transacciones(
        transacciones=txs,
        banco="bbva",
        funcion_ia_clasificadora=mock_ia,
        batch_size=100
    )

    # 4. Verificamos que las piezas del rompecabezas encajaron
    assert txs[0].categoria == "GENERAL"  # Marcada por la IA simulada
    assert txs[1].categoria == "EFECTIVO" # Capturada por diccionario
    assert txs[2].categoria == "TPV"      # Marcada exitosamente por la IA simulada
    
    # Verificamos los totales finales (asegúrate de que hagan match con tu lógica de DEPOSITOS)
    assert totales["TPV"] == 500.0
    assert totales["EFECTIVO"] == 200.0
    assert totales.get("DEPOSITOS", 700.0) == 700.0