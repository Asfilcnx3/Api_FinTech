from enum import Enum
from .helpers_texto_fluxo import (
    PALABRAS_EXCLUIDAS,
    PALABRAS_COMISION_CREDITO,
    PALABRAS_COMISION_DEBITO,
    PALABRAS_COMISION_AMEX,
    PALABRAS_COMISION_TPV_GENERICA,
    PALABRAS_TPV,
    PALABRAS_TRASPASO_FINANCIAMIENTO,
    PALABRAS_PAGO_FINANCIAMIENTO,
    PALABRAS_TRASPASO_ENTRE_CUENTAS,
    PALABRAS_EFECTIVO,
    PALABRAS_BMRCASH,
    PALABRAS_TRASPASO_MORATORIO
)

# --- NUEVO ECOSISTEMA DE CLASIFICACIÓN (MOTOR HÍBRIDO) ---

class CategoriaTag(str, Enum):
    """
    Definición estricta de Tags. Usar Enums mejora el rendimiento en comparaciones 
    dentro de listas y diccionarios durante el multiprocesamiento.
    """
    EXCLUIDA = "EXCLUIDA"
    IVA = "IVA"
    COMISION_CR = "COMISION_CR"
    COMISION_DB = "COMISION_DB"
    COMISION_AMEX = "COMISION_AMEX"
    COMISION_MIXTA = "COMISION_MIXTA"
    TPV = "TPV"
    FINANCIAMIENTO = "FINANCIAMIENTO"
    PAGO_FINANCIAMIENTO = "PAGO_FINANCIAMIENTO"
    TRASPASO = "TRASPASO"
    EFECTIVO = "EFECTIVO"
    BMRCASH = "BMRCASH"
    MORATORIOS = "MORATORIOS"

# Configurador de Pesos y Diccionarios. 
# El peso se utiliza ÚNICAMENTE para la Fase 3 (Desempate heurístico) 
# si la Matriz de Conflictos no entra en acción.
CONFIGURACION_TAGS = {
    CategoriaTag.EXCLUIDA: {
        "peso": 9999, # Peso infinito, detiene la evaluación
        "palabras": PALABRAS_EXCLUIDAS
    },
    CategoriaTag.IVA: {
        "peso": 1000,
        "palabras": ["iva"] # Agregado directo ya que lo tenías hardcodeado en el motor
    },
    CategoriaTag.COMISION_CR: {
        "peso": 100,
        "palabras": PALABRAS_COMISION_CREDITO
    },
    CategoriaTag.COMISION_DB: {
        "peso": 100,
        "palabras": PALABRAS_COMISION_DEBITO
    },
    CategoriaTag.COMISION_AMEX: {
        "peso": 100,
        "palabras": PALABRAS_COMISION_AMEX
    },
    CategoriaTag.COMISION_MIXTA: {
        "peso": 90,
        "palabras": PALABRAS_COMISION_TPV_GENERICA
    },
    CategoriaTag.TPV: {
        "peso": 80,
        "palabras": PALABRAS_TPV
    },
    CategoriaTag.FINANCIAMIENTO: {
        "peso": 50,
        "palabras": PALABRAS_TRASPASO_FINANCIAMIENTO
    },
    CategoriaTag.PAGO_FINANCIAMIENTO: {
        "peso": 50,
        "palabras": PALABRAS_PAGO_FINANCIAMIENTO
    },
    CategoriaTag.TRASPASO: {
        "peso": 40,
        "palabras": PALABRAS_TRASPASO_ENTRE_CUENTAS
    },
    CategoriaTag.EFECTIVO: {
        "peso": 30,
        "palabras": PALABRAS_EFECTIVO
    },
    CategoriaTag.BMRCASH: {
        "peso": 30,
        "palabras": PALABRAS_BMRCASH
    },
    CategoriaTag.MORATORIOS: {
        "peso": 20,
        "palabras": PALABRAS_TRASPASO_MORATORIO
    }
}