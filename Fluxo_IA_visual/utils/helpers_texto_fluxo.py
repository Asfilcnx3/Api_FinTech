import re # EN ESTE ARCHIVO IRÁN TODOS LOS HELPERS DE TEXTO PARA FLUXO

# Creamos las palabras clave para verificar si un archivo es analizado o escaneado
PALABRAS_CLAVE_VERIFICACION = re.compile(
    r"banco|banca|cliente|estado de cuenta|rfc|periodo"
)

# Creamos la lista e palabras excluidas
PALABRAS_EXCLUIDAS = ["comision", "iva", "com.", "-com x", "cliente stripe", "imss", "spei recibidove por mas", "spei recibidomifel"]

# Creamos la lista de palabras clave generales (quitamos mit y american express)
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "payclip, s. de r.l. de c.v", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup", "deposito efectivo", "deposito en efectivo", "dep.efectivo", "deposito efectivo corresponsal", "traspaso entre cuentas", "anticipo de ventas", "anticipo de venta", "financiamiento", "credito"
]

PALABRAS_EFECTIVO = [
    "deposito efectivo", "deposito en efectivo", "dep.efectivo", "deposito efectivo corresponsal"
]

PALABRAS_TRASPASO_ENTRE_CUENTAS = [
    "traspaso entre cuentas", "traspaso cuentas propias", "traspaso entre cuentas propias", "transferencia entre cuentas propias", "transferencia entre cuentas", "traspaso entre mis cuentas", "traspaso a cuenta propia", "transferencia a cuenta propia", "traspaso a mis cuentas", "transferencia a mis cuentas", "transferencia cuentas propias"
]   

PALABRAS_TRASPASO_FINANCIAMIENTO = [
    "prestamo", "anticipo de ventas", "anticipo de venta", "financiamiento", "anticipo", "adelanto", "adelanto de ventas", "préstamo", "crédito", "otorgamiento de crédito", "comision por apertura"
]

PALABRAS_BMRCASH = [
    "bmrcash ref", "bmrcash"
]

PALABRAS_TRASPASO_MORATORIO = [ # Faltan ejemplos
    "cargo por moratorio", "intereses moratorios", "recargo", "recargos", "penalización", "penalizaciones", "pena convencional", "penalizacion", "penalizaciones convencionales", "cargo por moratorios", "interes moratorio", "cargo por intereses moratorios", "recargo por intereses moratorios"
]

# Definimos los campos esperados y sus tipos (No funcionan aún)
CAMPOS_STR = [
    "banco", "rfc", "nombre_cliente", "clabe_interbancaria", "periodo_inicio", "periodo_fin", "tipo_moneda"
    
]

CAMPOS_FLOAT = [
    "comisiones", "depositos", "cargos", "saldo_promedio", "depositos_en_efectivo", "entradas_TPV_bruto", "entradas_TPV_neto"
]

KEYWORDS_COLUMNAS = {
    # Agregamos singulares y variantes comunes sin espacios al inicio
    "cargo": [
        "retiro", "retiros", 
        "cargo", "cargos", 
        "debito", "debitos", 
        "débito", "débitos",
        "signo", "debe", 
        "salida", "salidas"
    ],
    "abono": [
        "deposito", "depositos",
        "depósito", "depósitos",
        "abono", "abonos", 
        "credito", "creditos", 
        "haber", "entrada", "entradas"
    ]
}

# ==========================================
# 1. CONFIGURACIÓN DE TERMINALES (REESTRUCTURADA)
# ==========================================

# A. AGREGADORES (Globales: Aparecen en cualquier banco)
AGREGADORES_MAPPING = {
    "BILLPOCKET": ["billpocket", "deposito pocketgroup", "deposito billpocket", "deposito bpu", "pocketgroup", "pocket de latinoamerica sapi de cv", "pocket de latinoamérica, s.a.p.i de c.v."],
    "GETNET": ["getnet"],
    "FISERV": ["fiserv", "first data", "firstdata"],
    "SR PAGO": ["sr pago", "srpago"],
    "KIWI": ["kiwi", "kiwi bop sa de cv", "kiwi international payment technologies"],
    "CLIP": ["clip"],
    "MENTA": ["menta"],
    "ZETTLE": ["zettle", "izettle", "izettle by paypal", "zettle by pay pal", "zettle by paypal"],
    "MERCADO PAGO": ["mercado pago", "mercadopago"],
    "MP AGREGADOR": ["mp agregador", "blue point"],
    "NET PAY": ["net pay", "netpay"],
    "SMPS": ["smps"],
    "WUZI": ["wuzi"],
    "VELPAY": ["velpay"],
    "EVOPAY": ["evopay mx", "evopay", "deposito ventas netas por evopaymx", "deposito ventas netas d tar", "deposito ventas netas d amex"]
}

# B. TERMINALES BANCARIAS (Contextuales: Solo se buscan si estamos en ese banco)
# Las llaves deben coincidir con el nombre estandarizado del banco que devuelve tu IA/Regex
TERMINALES_BANCO_MAPPING = {
    "BANBAJIO": ["deposito negocios afiliados"],
    "BBVA": ["terminales punto de venta", "tdc inter", "ventas crédito", "ventas débito", "ventas nal. amex", "ventas nal amex"],
    "AFIRME": ["venta tpv cr", "venta tpv db", "venta tpvcr", "venta tpvdb"],
    "HSBC": ["venta tpv hsbc", "ventatpv hsbc", "venta tpvhsbc", "venta tpv cr hsbc", "venta tpv db hsbc", "venta tpvcr hsbc", "venta tpvdb hsbc", "transf rec hsbcnet tpv cr", "transf rec hsbcnet tpv db", "transf rec hsbcnet tpvcr", "transf rec hsbcnet tpvdb"],
    "MIFEL": ["venta tpv mifel", "ventatpv mifel", "venta tpvmifel", "venta tpv cr mifel", "venta tpv db mifel", "venta tpvcr mifel", "venta tpvdb mifel", "transf rec mifelnet tpv cr", "transf rec mifelnet tpv db", "transf rec mifelnet tpvcr", "transf rec mifelnet tpvdb"],
    "SCOTIABANK": ["amexco se", "american express company mexico", "american express company"],
    "BANREGIO": ["abono ventas tdd", "abono ventas tdc", "abono ventastdd", "abono ventastdc"],
    "SANTANDER": ["deposito ventas del día afil", "deposito ventas del dia afil"],
    "MULTIVA": ["ventas tpvs", "ventas tdd", "ventas tdc", "ventas tarjetas", "ventas tdc inter", "venta credito", "ventas debito"],
    # BANORTE se maneja por Regex especial, pero podemos poner palabras clave extra si existen
    "BANORTE": [] 
}

CONFIGURACION_BANCOS = {
    "banorte": {
        "alias": ["banco mercantil del norte"],
        "rfc_pattern": [r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total de comisiones cobradas / pagadas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"total de depósitos\s*\$\s*([\d,]+\.\d{2})"]
    },
    "banbajío": {
        "alias": ["banco del bajio", "banco del bajío"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})"]
    },
    "afirme": {
        "alias": ["banca afirme"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total de comisiones\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s+\$\s*([\d,]+\.\d{2})"]
    },
    "hsbc": {
        "alias": ["grupo financiero hsbc"],
        "rfc_pattern": [r"rfc[^\n]*\n\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"], # Versión multilínea
        "comisiones_pattern": [r"comisiones cobradas(?: en el mes)? \$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[éeóo]sitos/? \$ ([\d,]+\.\d{2})"]
    },
    "mifel": {
        "alias": ["grupo financiero mifel"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"[0-9]\.\s*dep[óo]sitos\s+\$?([\d,]+(?:\.\d{2})?)"]
    },
    "scotiabank": {
        "alias": ["scotiabank inverlat"],
        "rfc_pattern": [r"r\.*\s*f\.*\s*c\.*\s*cliente\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones\s*cobradas\s*\$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"\(\+\)\s*dep[óo]sitos\s*\$([\d,]+\.\d{2})"]
    },
    "banregio": {
        "alias": ["banco regional"],
        "rfc_pattern": [r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"(?:\+?\s*abonos)\s*\$([\d,]+\.\d{2})"]
    },
    "bbva": {
        "alias": ["grupo financiero bbva"],
        "rfc_pattern": [r"r\.f\.c\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total comisiones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[óo]sitos\s*/\s*abonos\s*\(\+\)\s*\d+\s+([\d,]+\.\d{2})"]
    },
    "multiva": {
        "alias": ["banco multiva"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas\/bonificaciones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"retiros\/depósitos\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})"]
    },
    "santander": {
        "alias": ["banco santander", "bancosantander"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas\s*.+?\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"(?:dep.{0,10}sitos)\s*\$?([\d,]+\.\d{2})"]
    },
    "banamex": {
        "alias": ["banco nacional de mexico", "banco nacional de méxico", "domiciliación banamex"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "citibanamex":{
        "alias": ["citibanamex"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "bancrea": {
        "alias": ["banco bancrea"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas en el per[ií]odo\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "inbursa": {
        "alias": ["banco inbursa"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"en el periodo\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"abonos\s*([\d,]+\.\d{2})"]
    },
    "monex": {
        "alias": ["banco monex"],
        "rfc_pattern": [r"rfc titular:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"total abonos:\s*([\d,]+\.\d{2})"]
    },
    "azteca": {
        "alias": ["banco azteca"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones[\s\S]*?\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos[\s\S]*?\$\s*([\d,]+\.\d{2})"]
    },
    "bankaool": {
        "alias": ["bankaool"],
        "rfc_pattern": [r"rfc\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas[\s\S]*?\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos[\s\S]*?\$\s*([\d,]+\.\d{2})"]
    },
    "intercam": {
        "alias": ["intercuenta enlace intercam"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[éeóo]sitos\s*([\d,]+\.\d{2})"]
    },
    "vepormas": {
        "alias": ["grupo financiero ve por más", "grupo financiero ve por mas"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"r\.f\.c\.\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    }
}

ALIAS_A_BANCO_MAP = {}

# Crear un mapa de alias a nombre estándar ("banco del bajio" -> "banbajío")
for nombre_std, config in CONFIGURACION_BANCOS.items():
    # Añadimos el Alias
    for alias in config["alias"]:
        ALIAS_A_BANCO_MAP[alias] = nombre_std

# Compilar la regex para detectar CUALQUIER nombre de banco
BANCO_DETECTION_REGEX = re.compile("|".join(ALIAS_A_BANCO_MAP.keys()))

PATRONES_COMPILADOS = {}
for nombre_str, config in CONFIGURACION_BANCOS.items():
    PATRONES_COMPILADOS[nombre_str] = {} # Inicializa el diccionario para el banco
    
    # Itera dinámicamente sobre todas las claves de patrones (rfc_pattern, comisiones_pattern, etc.)
    for key, pattern_list in config.items():
        if key.endswith("_pattern"):
            if not pattern_list:
                continue
            
            # UNIMOS LA LISTA ED PATRONES EN UNA SOLA REGEX "|" y lo envolvimos en (?:...)
            patron_combinado = "|".join(f"(?:{p})" for p in pattern_list)

            # Guardamos el patrón compilado con un nombre de clave limpio (sin '_pattern')
            nombre_clave = key.replace("_pattern", "")
            PATRONES_COMPILADOS[nombre_str][nombre_clave] = re.compile(patron_combinado)

# Configuración de triggers más robusta
TRIGGERS_CONFIG = {
    # Palabras que indican INEQUÍVOCAMENTE que empieza una cuenta
    "inicio": [
        'la gat real es el rendimiento que obtendría después de descontar la inflación estimada"',
        'detalle de la cuenta',
        'detalle de movimientos realizados'
    ],
    # Palabras que indican el FINAL (generalmente pies de página legales o timbres SAT)
    "fin": [
        'este documento es una representación impresa de un cfdi',
        'total de movimientos'
    ]
}

# Creamos el prompt del modelo a utilizar
prompt_base_fluxo = """
Eres un experto extractor de datos de estados de cuenta bancarios. 
- Estas imágenes son de las primeras páginas de un estado de cuenta bancario, pueden venir gráficos o tablas.
- En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Analizarás las imágenes en líneas horizontales y extraerás EXACTAMENTE los siguientes datos con las instrucciones siguientes.
INSTRUCCIONES CRÍTICAS (CAMPOS A EXTRAER):
1. NOMBRE DEL BANCO: Busca cerca de "Banco:", "Institución:", o en el encabezado. Debe ser el nombre corto, por ejemplo, "banco del bajío" es banbajío.
2. TIPO DE MONEDA: Busca cerca de "Moneda:", "Tipo de moneda:", o en la sección de resumen. Debe ser su versión resumida como "MXN" para pesos mexicanos o "USD" para dólares estadounidenses EUR para euros, etc.
3. NOMBRE DEL CLIENTE: Busca cerca de "Titular:", "Cliente:", o "Razón Social:". Es el texto en mayúsculas después de estas palabras.
4. CLABE: Son EXACTAMENTE 18 dígitos (pueden ser consecutivos o tener un espacio antes del último dígito). Busca cerca de "CLABE", "Clabe Interbancaria" o en la sección de datos de cuenta, puede estar en horizontal o vertical cerca de las palabras.
5. RFC: Son 12-13 caracteres alfanuméricos. Busca cerca de "RFC:", "R.F.C." o después del nombre.
6. PERIODO DE INICIO: La primera fecha del periodo en formato "YYYY-MM-DD".
7. PERIODO DE FIN: La segunda fecha del periodo en formato "YYYY-MM-DD".
8. COMISIONES: Busca "Comisiones", "Cargos por servicio", o "Total comisiones". Toma el valor numérico más grande.
9. CARGOS: Busca "Cargos", "Retiros", o "Total cargos". Toma el valor numérico más grande.
10. DEPÓSITOS: Busca "Depósitos", "Abonos", o "Total depósitos". Toma el valor numérico más grande.
11. SALDO PROMEDIO: Busca "Saldo promedio", "Saldo medio", o "Saldo promedio del periodo".

FORMATO DE RESPUESTA (JSON):
```json
{
    "banco": "NOMBRE_BANCO",
    "tipo_moneda": "MXN",
    "nombre_cliente": "NOMBRE COMPLETO EN MAYUSCULAS",
    "clabe_interbancaria": "012345678901234567",
    "rfc": "XXX000000XXX",
    "periodo_inicio": "YYYY-MM-DD",
    "periodo_fin": "YYYY-MM-DD",
    "comisiones": 123.45,
    "cargos": 123.45,
    "depositos": 123456.78,
    "saldo_promedio": 123456.78
}
```

REGLAS IMPORTANTES:
- Ignora cualquier otra parte del documento. No infieras ni estimes valores. Si NO encuentras un dato, usa null (no inventes).
- Extrae los campos si los ves y devuelve únicamente un JSON.
- Para fechas, usa formato YYYY-MM-DD.
- Los valores tipo string deben de estar COMPLETO y en MAYÚSCULAS.
- Para montos, solo números con decimales (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.
"""

PROMPT_FASE_2_ESCRIBA_TEXTO = """
TU OBJETIVO:
Eres un transcriptor financiero especializado en estados de cuenta bancarios. Tu ÚNICA tarea será convertir el texto en transacciones estructuradas en formato TOON.
No clasifiques, solo transcribe los movimientos que encuentres. Para mejorar la precisión, tu entrada es texto estructurado en líneas horizontales, cada línea representa una fila del estado de cuenta.

FORMATO DE SALIDA (TOON):
1. Una línea por transacción.
2. Separador obligatorio: `|` (pipe).
3. Estructura EXACTA:
    FECHA | DESCRIPCION | MONTO

    - FECHA: solo el número del día (dos dígitos, ej. 05).
    - DESCRIPCION: solo el texto del concepto unido en UNA sola línea.
    - MONTO: número decimal limpio (sin comas, sin símbolo $).

REGLAS DE IDENTIFICACIÓN DE TRANSACCIONES:
1. Una transacción puede ocupar VARIAS líneas consecutivas.
2. La transacción comienza cuando aparece una línea con una o varias fechas visibles (ej. 05/ago o '05 05').
3. Todas las líneas siguientes SIN FECHA pertenecen a la MISMA transacción hasta que aparezca otra fecha.
4. La fecha válida es SIEMPRE la PRIMERA fecha que aparece en la línea, descarta la segunda si existe.
5. Pueden haber varios movimientos similares o iguales en el mismo día, cada uno es una transacción separada, siempre y cuando tenga una fecha.

REGLAS PARA DESCRIPCION:
- Une TODAS las líneas del concepto de la transacción en una sola descripción.
- Respeta el orden del texto.
- No elimines palabras.
- Si el texto está cortado después de tener el monto, déjalo cortado.
- si el texto está cortado sin tener el monto, ignora la transacción.
- No inventes información.

REGLAS CRÍTICAS PARA MONTO:
1. Una transacción puede contener UNO, DOS o TRES montos en la misma línea.
2. El MONTO REAL de la operación es SIEMPRE:
    - EL PRIMER MONTO NUMÉRICO QUE APARECE DE IZQUIERDA A DERECHA EN LA TRANSACCIÓN y no es parte de la descripción.
3. Ignora TODOS los montos que aparezcan DESPUÉS de ese primer monto. (estos suelen ser saldos o montos de liquidación).
4. Nunca uses montos de columnas de saldo ni de la descripción.
5. SI NO PUEDES IDENTIFICAR CLARAMENTE UN MONTO DE OPERACIÓN, IGNORA LA TRANSACCIÓN.

REGLAS DE FILTRADO:
- Ignora encabezados, pies de página, totales y saldos.
- Ignora filas sin monto válido.
- No dupliques transacciones.
- No generes líneas vacías.

EJEMPLO DE SALIDA:
05 | t20 spei recibidobanregio 0050825 traspaso a cf moto mty ref 0173214373 058 00058580094678400183 058-05/08/2025/05-009roqb077 cfmoto monterrey s.a. de c.v. | 1060000.00
05 | n06 pago cuenta de tercero bnet 1551474581 manuel alanis ref 0031589758 | 2050.00
"""

PROMPT_FASE_2_ESCRIBA_VISION = """
TU OBJETIVO:
Eres un sistema OCR financiero experto en leer tablas de estados de cuenta bancarios. Tu ÚNICA tarea será convertir el texto en transacciones estructuradas en formato TOON.
No clasifiques, solo transcribe los movimientos que encuentres siguiendo las reglas visuales estrictas a continuación.

FORMATO DE SALIDA (TOON):
1. Una línea por transacción.
2. Separador obligatorio: `|` (pipe).
3. Estructura EXACTA:
FECHA | DESCRIPCION | MONTO | TIPO

- FECHA: solo el número del día (dos dígitos, ej. 05).
- DESCRIPCION: todo el texto del concepto unido en UNA sola línea.
- MONTO: número decimal limpio (sin comas, sin símbolo $).
- TIPO: "abono" o "cargo" según la columna visual a la que pertenece el movimiento.
    Posibles columnas:
    Abonos = depósitos / entradas / abonos
    Cargos = retiros / salidas / cargos

REGLAS VISUALES DE TRANSACCIÓN:
1. Cada transacción comienza en una fila donde aparece una o varias fechas.
2. Una sola transaccion puede ocupar VARIAS líneas consecutivas.
3. Las líneas debajo sin fecha pertenecen a la MISMA transacción hasta que aparezca otra fecha.
4. Une todas las líneas hasta encontrar otra linea con fechas.
5. La fecha válida es SIEMPRE la PRIMERA fecha que aparece en la línea, descarta la segunda si existe.
6. Pueden haber varios movimientos similares o iguales en el mismo día, cada uno es una transacción separada, siempre y cuando tenga una fecha.

REGLAS CRÍTICAS PARA MONTO:
1. Una fila puede mostrar VARIOS montos (operación + saldos).
2. El MONTO REAL es:
    - EL PRIMER MONTO NUMÉRICO DE IZQUIERDA A DERECHA EN LA TRANSACCIÓN QUE ESTÉ ALINEADO CON LA COLUMNA DEPÓSITOS O RETIROS.
3. Ignora montos alineados con columnas de SALDO.
4. Si aparecen 2 o 3 montos:
    - Usa SOLO que pertenezca a la columna de depósitos o retiros.
    - Ignora los demás.
    - Si ninguno pertenece a esas columnas, ignora la transacción.
5. SI NO PUEDES IDENTIFICAR CLARAMENTE UN MONTO DE OPERACIÓN, IGNORA LA TRANSACCIÓN.

REGLAS PARA TIPO:
- Si el monto está bajo la columna "depósitos" / "abonos" / "entradas":
    → TIPO = "abono"
- Si el monto está bajo "retiros" / "cargos" / "salidas":
    → TIPO = "cargo"

REGLAS DE PRECISIÓN:
- Sé extremadamente preciso con los números.
- Ignora encabezados, pies de página, totales y saldos.
- No cambies decimales.
- No inventes montos.
- Ignora filas sin monto válido.
- No dupliques transacciones.
- No generes transacciones falsas ni lineas vacías.

EJEMPLO DE SALIDA:
05 | n06 pago cuenta de tercero bnet 1551474581 manuel alanis ref 0031589758 | 2050.00 | abono
05 | comision manejo cuenta | 50.00 | cargo
"""

PROMPT_FASE_3_AUDITOR_TEMPLATE = """
TU ROL: Eres un Analista de Riesgos y Fraude especializado en TPVs (Terminales Punto de Venta).
TU OBJETIVO: Clasificar una lista de transacciones bancarias basándote estrictamente en las reglas proporcionadas.

CONTEXTO:
Banco del documento: {banco}

--------------------------------------------------
REGLAS DE CLASIFICACIÓN APLICABLES (CRÍTICO):

{reglas_especificas}

--------------------------------------------------
INSTRUCCIONES DE SALIDA:
Recibirás una lista JSON: [{{"id": 1, "desc": "..."}}]
Devuelve ÚNICAMENTE un JSON válido mapeando ID a ETIQUETA.
Las etiquetas permitidas son: "TPV", "GENERAL", "EFECTIVO".

EJEMPLO OUTPUT:
{{
    "0": "TPV",
    "1": "GENERAL"
}}
"""

PROMPT_GENERICO = """
    Las transacciones TPV válidas contienen lo siguiente en su concepto:
    Reglas de la extracción, puede ser una o varias líneas:
        - evopay
        - evopayments
        - psm payment services mexico sa de cv
        - deposito bpu y 10 numeros
        - cobra online s.a.p.i. de c.v.
        - sr. pago
        - por favor paguen a tiempo, s.a. de c.v.
        - por favor paguen a tiempo
        - pagofácil
        - netpay s.a.p.i. de c.v.
        - netpay
        - deremate.com de méxico, s. de r.l. de  c.v.
        - mercadolibre s de rl de cv
        - mercado lending, s.a de c.v
        - first data merchant services méxico s. de r.l. de c.v
        - adquira méxico, s.a. de c.v
        - payclip, s. de r.l. de c.v
        - pocket de latinoamérica, s.a.p.i de c.v.
        - billpocket
        - pocketgroup
        - evo payments
        - net pay sa de cv
        - net pay sapi de cv
        - izettle méxico, s. de r.l. de c.v.
        - izettle mexico s de rl de cv
        - pocket de latinoamerica sapi de cv
        - bn-nts
        - izettle mexico s de rl
        - first data merc
        - cobra online sapi de cv
        - payclip s de rl de cv
        - evopaymx
        - izettle
        - refbntc00017051
        - pocket de
        - sofimex
        - actnet
        - exce cca
        - venta nal. amex
        - pocketgroup
    """

PROMPTS_POR_BANCO = {
    "bbva": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO BBVA

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - venta tarjetas
    - venta tdc inter
    - ventas crédito
    - ventas debito
    - ventas nal. amex

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - t20 spei recibido banorte
    - t20 spei recibido santander
    - t20 spei recibido afirme
    - t20 spei recibido hsbc
    - t20 spei recibido citi mexico
    - spei recibido banorte
    - t20 spei recibidostp
    - w02 spei recibidosantander
    - deposito de tercero
    - t20 spei recibido jpmorgan

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - deposito bpu
    - mp agregador s de rl de cv
    - anticipo {nombre comercial}
    - 7 dígitos y 'af'
    - 7 dígitos y 'sq'
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
    - bmrcash ref
    - zettle by paypal
    - pw online mexico sapi de cv
    - liquidacion wuzi

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
""",

    "banbajío": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO BANBAJÍO

IMPORTANTE:
- Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
- SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
- CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - deposito negocios afiliados 
    - deposito negocios afiliados adquiriente
    - deposito negocios afiliados adquiriente optblue amex

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
- Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
- Nunca marques "tpv" si no estás completamente seguro.
    """,

    "banorte": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO BANORTE

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):
    - 8 numeros y luego una c
    - 8 numeros y luego una d
    - dep. efectivo

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - spei recibido
    - traspaso de cta
    - spei recibido del cliente red amigo
    - pago recibido de banorte por
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - ganancias clip
    - clip
    - amexco
    - orden de netpay sapi de cv
    - dal sapi de cv
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "afirme": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO AFIRME

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas): 

    - venta tpv cr
    - venta tpv db
    - venta tpvcr
    - venta tpvdb
    - deposito efectivo
    - deposito en efectivo
    - dep.efectivo

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "hsbc": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO HSBC

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - transf rec hsbcnet tpv db
    - transf rec hsbcnet tpv cr
    - transf rec hsbcnet dep tpv
    - deposito bpu y 10 numeros
    - transf rec hsbcnet dep tpv (comnibaciones de numeros)
    - deposito bpu (varias combinaciones)

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "mifel": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO MIFEL

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):
    - vta. cre y 2 secciones de numeros
    - vta. deb y 2 secciones de numeros
    - vta cre y 2 secciones de numeros
    - vta deb y 2 secciones de numeros

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - vta deb
    - vta cre
    - transferencia spei
    - transferencia spei bn
    - transferencia spei entre
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - dispersion de fondos
    - cuentas
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "scotiabank": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO SCOTIABANK

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA 
Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento"

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - transf interbancaria spei
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - transf interbancaria spei
    - deposito bpu
    - amexco se
    - dep
    - pocket de latinoamerica sapi
    - first data merchant services m
    - american express company mexico
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "banregio": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO BANREGIO

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):
    - abono ventas tdd 
    - abono ventas tdc

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - billpocket
    - deposito spei
    - spei banorte

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - pocket de latinoamerica sapi de cv
    - net pay sapi de cv
    - deposito bpu y 10 numeros
    - bn-nts y 6 digitos
    - cobra online sapi de cv
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "santander": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO SANTANDER

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - deposito ventas del dia afil

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - abono transferencia spei hora

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - de la cuenta
    - recibido de stp
    - deposito spei
    - deposito bpu
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "multiva": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO MULTIVA

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - ventas tpvs 
    - venta tdd
    - venta tdc
    - ventas tarjetas
    - ventas tdc inter
    - ventas credito 
    - ventas debito

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - spei recibido stp
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - latinoamerica sapi de cv
    - deposito bpu y 10 numeros
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "citibanamex": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO CITIBANAMEX

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - deposito ventas netas por evopaymx
    - deposito ventas netas

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:
    - deposito ventas netas d tar
    - deposito ventas netas d amex
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:

    - por evopay
    - suc
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "banamex": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO BANAMEX

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA (DESCRIPCIÓN CONTIENE FRASE EXACTA)
La descripción debe contener EXACTAMENTE alguna de las siguientes frases (ignorando mayúsculas/minúsculas):

    - deposito ventas netas por evopaymx
    - deposito ventas netas
    - BN-NTS y 6 digitos

Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - deposito ventas netas d tar
    - deposito ventas netas d amex
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - por evopay
    - suc
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "azteca": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO AZTECA

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA 
Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - transferencia spei a su favor
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - emisor: banorte
    - emisor: santander
    - payclip s de rl decv
    - gananciasclip
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "inbursa": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO INBURSA

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA 
Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:

    - kiwi international payment technologies
    - cobra online sapi de cv
    - operadora paypal de mexico s de rl
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - zettle by paypal
    - payclip s de rl decv
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "intercam": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO INTERCAM

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA 
Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - recepcion spei jp morgan
    - recepcion spei santander
    - recepcion spei banorte
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:
    - 136180018635900157
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - payclip s de rl decv
    - gananciasclip

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,

    "vepormas": """ 
REGLAS EXCLUSIVAS DE CLASIFICACIÓN TPV - BANCO AZTECA

IMPORTANTE:
    - Estas reglas SOLO aplican para decidir la columna `ETIQUETA`.
    - SOLO las transacciones con TIPO = "abono" pueden ser etiquetadas como "tpv".
    - CUALQUIER transacción con TIPO = "cargo" debe ser "general".

CRITERIOS PARA ETIQUETA = "TPV"
Una transacción (abono) debe marcarse como "tpv" SI Y SOLO SI cumple AL MENOS UNO de los siguientes criterios:

A) REGLAS DE UNA SOLA LÍNEA 
Si la descripción contiene cualquiera de estas palabras clave:
    - financiamiento
    - credito
    - traspaso entre cuentas

Deberá marcarse con la misma palabra clave, traspaso entre cuentas es "traspaso entre cuentas", credito es "crédito" y financiamiento es "financiamiento".

B) REGLAS MULTILÍNEA (TRANSACCIÓN COMPUESTA)
Una transacción multilínea debe marcarse como "tpv" SI Y SOLO SI:
1) La PRIMERA línea de la transacción contiene EXACTAMENTE alguna de estas frases:

    - recepcion spei jp morgan
    - recepcion spei santander
    - recepcion spei banorte
    - deposito spei

Y ADEMÁS
2) AL MENOS UNA de las líneas siguientes de LA MISMA TRANSACCIÓN contiene alguna de estas frases:

    - 136180018635900157
    - cobra online sapi de cv
    - bn-nts 6 digitos
    - pw online mexico sapi de cv
    - liquidacion wuzi
    - deposito bpu
    - mp agregador s de rl de cv
    - trans sr pago
    - net pay sapi de cv
    - getnet mexico servicios de adquirencia s
    - payclip s de rl de cv
    - pocket de latinoamerica sapi de cv
    - kiwi bop sa de cv
    - kiwi international payment technologies
    - zettle by paypal
    - payclip s de rl decv
    - gananciascliP

REGLA DE EXCLUSIÓN ABSOLUTA:
    - Cualquier otro depósito SPEI
    - Transferencias de otros bancos
    - Pagos de nómina
    - Traspasos que NO cumplan exactamente las reglas anteriores
DEBEN ser etiquetados como "general".

REGLA DE SEGURIDAD:
    - Si existe cualquier duda, ambigüedad o conflicto, usa siempre "general".
    - Nunca marques "tpv" si no estás completamente seguro.
    """,
}