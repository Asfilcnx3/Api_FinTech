## EN ESTE ARCHIVO IRÁN PRUEBAS DE FUNCIONES QUE YA NO SE USAN, PERO QUE PODRÍAN SER ÚTILES EN EL FUTURO

from procesamiento.auxiliares import verificar_total_depositos # ya no existe la carpeta procesamiento


def test_verificar_total_depositos(): # ya no existe la función verificar_total_depositos
    """Probamos la lógica de la suma de los depósitos"""
    # Caso 1: La suma es mayor a 250,000
    datos_mayor = [{"depositos": 200000.0}, {"depositos": 60000.0}]
    assert verificar_total_depositos(datos_mayor) is True

    # Caso 2: La suma es menor a 250,000
    datos_menor = [{"depositos": 100000.0}, {"depositos": 20000.0}]
    assert verificar_total_depositos(datos_menor) is False

    # Caso 3: Faltan datos o son nulos
    datos_vacios = [{"depositos": 10000.0}, {"otro_campo":50000.0}, {"depositos": None}]
    assert verificar_total_depositos(datos_vacios) is False


"""
CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas: 
        Reglas de la extracción de una línea: 
            - venta tarjetas
            - venta tdc inter
            - ventas crédito
            - ventas débito 
            - financiamiento # si aparece esta palabra, colocala en la salida
            - credito # si aparece esta palabra, colocala en la salida
            - ventas nal. amex
        Reglas de la extracción multilinea, para que sea válida debe cumplir con ambas condiciones en la misma transacción:
            la primer línea debe contener:
            - t20 spei recibido santander, banorte, stp, afirme, hsbc, citi mexico
            - spei recibido banorte
            - t20 spei recibidostp
            - w02 spei recibidosantander
            - traspaso ntre cuentas
            - deposito de tercero
            - t20 spei recibido jpmorgan
            - traspaso entre cuentas propias
            - traspaso cuentas propias
            las demás líneas deben contener:
            - deposito bpu
            - mp agregador s de rl de cv 
            - anticipo {nombre comercial}
            - 0000001af
            - 0000001sq
            - trans sr pago
            - dispersion sihay ref
            - net pay sapi de cv
            - getnet mexico servicios de adquirencia s
            - payclip s de rl de cv
            - pocket de latinoamerica sapi de cv
            - cobra online sapi de cv
            - kiwi bop sa de cv
            - kiwi international payment technologies
            - traspaso entre cuentas
            - deposito de tercero
            - bmrcash ref # si aparece esta palabra, colocala en la salida
            - zettle by paypal
            - pw online mexico sapi de cv
            - liquidacion wuzi
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba de forma exacta, son tratados como 'GENERALES'."""