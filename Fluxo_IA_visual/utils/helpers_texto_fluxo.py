import re # EN ESTE ARCHIVO IRÁN TODOS LOS HELPERS DE TEXTO PARA FLUXO

# Creamos las palabras clave para verificar si un archivo es analizado o escaneado
PALABRAS_CLAVE_VERIFICACION = re.compile(
    r"banco|banca|cliente|estado de cuenta|rfc|periodo"
)

# Creamos la lista e palabras excluidas
PALABRAS_EXCLUIDAS = ["comision", "iva", "com.", "-com x", "cliente stripe", "imss"]

# Creamos la lista de palabras clave generales (quitamos mit y american express)
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "payclip, s. de r.l. de c.v", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup", "deposito efectivo", "deposito en efectivo", "dep.efectivo", "deposito efectivo corresponsal", "traspaso entre cuentas", "anticipo de ventas", "anticipo de venta", "financiamiento", "credito"
]

PALABRAS_EFECTIVO = [
    "deposito efectivo", "deposito en efectivo", "dep.efectivo", "deposito efectivo corresponsal"
]

PALABRAS_TRASPASO_ENTRE_CUENTAS = [
    "traspaso entre cuentas", "traspaso cuentas propias", "traspaso entre cuentas propias"
]   

PALABRAS_TRASPASO_FINANCIAMIENTO = [
    "prestamo", "anticipo de ventas", "anticipo de venta", "financiamiento", "anticipo", "adelanto", "adelanto de ventas", "préstamo", "crédito", "otorgamiento de crédito", "comision por apertura"
]

PALABRAS_BMRCASH = [
    "bmrcash ref", "bmrcash"
]

PALABRAS_TRASPASO_MORATORIO = [ # Faltan ejemplos
    "cargo por moratorio", "intereses moratorios", "recargo", "recargos", "penalización", "pena", "penalizaciones", "pena convencional", "penalizacion", "penalizaciones convencionales", "cargo por moratorios", "interes moratorio", "cargo por intereses moratorios", "recargo por intereses moratorios"
]

# Definimos los campos esperados y sus tipos (No funcionan aún)
CAMPOS_STR = [
    "banco", "rfc", "nombre_cliente", "clabe_interbancaria", "periodo_inicio", "periodo_fin", "tipo_moneda"
    
]

CAMPOS_FLOAT = [
    "comisiones", "depositos", "cargos", "saldo_promedio", "depositos_en_efectivo", "entradas_TPV_bruto", "entradas_TPV_neto"
]

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
        "alias": ["banco nacional de mexico", "banco nacional de méxico"],
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
        'detalle de la cuenta'
    ],
    # Palabras que indican el FINAL (generalmente pies de página legales o timbres SAT)
    "fin": [
        "este documento es una representación impresa de un cfdi",
    ]
}

# Creamos el prompt del modelo a utilizar
prompt_base_fluxo = """
Eres un experto extractor de datos de estados de cuenta bancarios. Analiza las imágenes y extrae EXACTAMENTE los siguientes datos.
- Estas imágenes son de las primeras páginas de un estado de cuenta bancario, pueden venir gráficos o tablas.
- En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

INSTRUCCIONES CRÍTICAS (CAMPOS A EXTRAER):
1. NOMBRE DEL BANCO: Busca cerca de "Banco:", "Institución:", o en el encabezado. Debe ser el nombre corto, por ejemplo, "banco del bajío" es banbajío.
2. TIPO DE MONEDA: Busca cerca de "Moneda:", "Tipo de moneda:", o en la sección de resumen. Debe ser su versión resumida como "MXN" para pesos mexicanos o "USD" para dólares estadounidenses EUR para euros, etc.
3. NOMBRE DEL CLIENTE: Busca cerca de "Titular:", "Cliente:", o "Razón Social:". Es el texto en mayúsculas después de estas palabras.
4. CLABE: Son EXACTAMENTE 18 dígitos consecutivos. Busca cerca de "CLABE", "Clabe Interbancaria" o en la sección de datos de cuenta.
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

PROMPT_TEXTO_INSTRUCCIONES_BASE = """
INSTRUCCIONES DE FORMATO (TOON):
1.  NO USES JSON. Genera una salida de texto plano ultra-compacta.
2.  Una línea por transacción.
3.  Delimitador: Usa el caracter `|` (pipe) para separar los campos.
4.  Estructura: `FECHA | DESCRIPCION COMPLETA | MONTO | TIPO | ETIQUETA`
    * `FECHA`: ÚNICAMENTE EL NÚMERO DEL DÍA DE LA FECHA (ej. '02').
    * `DESCRIPCION`: Todo el texto del concepto.
    * `MONTO`: Solo números y puntos (ej. 1500.50).
    * `TIPO`: "cargo" o "abono".
    * `ETIQUETA`: "TPV" (si cumple las reglas) o "GENERAL" (si es cualquier otro movimiento).

INSTRUCCIONES CLAVE DE PROCESAMIENTO:
1. Ignora el inicio si está incompleto: Si el texto comienza a mitad de una transacción (por ejemplo, sin una fecha o referencia clara), ignora esa primera transacción incompleta. El fragmento anterior ya la procesó.
2. Extrae todo hasta el final: Procesa todas las transacciones que puedas identificar completamente. Si la *última* transacción del texto parece estar cortada o incompleta, extráela también. El siguiente fragmento se encargará de completarla y el sistema la deduplicará.
3.  Extrae TODOS los movimientos (gastos, cheques, comisiones, depósitos).
4.  Para la columna `ETIQUETA`, revisa minuciosamente las reglas del banco.
    * Si es un cargo, la etiqueta siempre es "GENERAL".
    * Si es un abono y cumple las reglas de palabras clave o multilínea, es "TPV".
5. Precisión Absoluta: Sé meticuloso con los montos y las fechas. No alucines información. Si un dato no está, déjalo como null.

EJEMPLO DE SALIDA, SIEMPRE EN MINUSCULAS:
05 | VENTAS TARJETAS 123456 | 15200.50 | abono | GENERAL
06 | COMISION POR APERTURA | 500.00 | cargo | TPV
"""

PROMPT_OCR_INSTRUCCIONES_BASE = """
INSTRUCCIONES DE FORMATO (TOON):
1.  NO USES JSON. Genera una salida de texto plano ultra-compacta.
2.  Una línea por transacción.
3.  Delimitador: Usa el caracter `|` (pipe) para separar los campos.
4.  Estructura: `FECHA | DESCRIPCION COMPLETA | MONTO | TIPO | ETIQUETA`
    * `FECHA`: ÚNICAMENTE EL NÚMERO DEL DÍA DE LA FECHA (ej. '02').
    * `DESCRIPCION`: Todo el texto del concepto.
    * `MONTO`: Solo números y puntos (ej. 1500.50).
    * `TIPO`: "cargo" o "abono".
    * `ETIQUETA`: "TPV" (si cumple las reglas) o "GENERAL" (si es cualquier otro movimiento).

INSTRUCCIONES CLAVE DE PROCESAMIENTO:
1.  Analiza las Imágenes de forma horizontal: Las siguientes imágenes son páginas de un estado de cuenta escaneado. Tu tarea es actuar como un OCR experto y un analista financiero analizano línea por línea los estados.
2. Extrae todo hasta el final: Procesa todas las transacciones que puedas identificar completamente. Si la *última* transacción del texto parece estar cortada o incompleta, extráela también. El siguiente fragmento se encargará de completarla y el sistema la deduplicará.
3.  Precisión Absoluta: Sé meticuloso con los montos y las fechas. No alucines información, si no ves campos es porque no los hay, dejalos como null.
4.  procesamiento secuencial obligatorio: Estás recibiendo solo una imagen. Debes extraer los datos de la Imagen 1. Hasta terminar con todas. NO TE SALTES NINGUNA transacción. Tu objetivo es transcribir CADA transacción visible. Si hay 50 transacciones en una página, debes generar 50 objetos toon. No resumas.

EJEMPLO DE SALIDA:
05 | DEPOSITO EFECTIVO SUC 02 | 5000.00 | abono | GENERAL
05 | CHEQUE PAGADO 001 | 2000.00 | cargo | GENERAL
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba de forma exacta, son tratados como 'GENERALES'.
    """,

    "banbajío": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea: 
            - deposito negocios afiliados 
            - deposito negocios afiliados adquiriente
            - deposito negocios afiliados adquiriente optblue amex
        
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - deposito spei
            
            alguna de las demás líneas deben contener:
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
    
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "banorte": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea: 
            - 8 numeros y luego una c
            - 8 numeros y luego una d
            - dep. efectivo
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - spei recibido
            - traspaso de cta
            - spei recibido del cliente red amigo
            - pago recibido de banorte por
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "afirme": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea: 
            - venta tpv cr
            - venta tpv db
            - venta tpvcr
            - venta tpvdb
            - deposito efectivo
            - deposito en efectivo
            - dep.efectivo
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
        la primer línea debe contener:
            - deposito spei
            
            alguna de las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "hsbc": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea: 
            - transf rec hsbcnet tpv db
            - transf rec hsbcnet tpv cr
            - transf rec hsbcnet dep tpv
            - deposito bpu y 10 numeros
            - transf rec hsbcnet dep tpv (comnibaciones de numeros)
            - deposito bpu (varias combinaciones)

        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
        la primer línea debe contener:
            - deposito spei
            
            alguna de las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "mifel": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - vta. cre y 2 secciones de numeros
            - vta. deb y 2 secciones de numeros
            - vta cre y 2 secciones de numeros
            - vta deb y 2 secciones de numeros
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - vta deb
            - vta cre
            - transferencia spei
            - transferencia spei bn
            - transferencia spei entre
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "scotiabank": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - transf interbancaria spei
            - deposito spei
            la segunda línea deben contener:
            - transf interbancaria spei
            - deposito bpu
            - amexco se
            - dep
            la tercera línea deben contener:
            - pocket de latinoamerica sapi
            - first data merchant services m
            - american express company mexico

            alguna de las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "banregio": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida como TPV si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - abono ventas tdd 
            - abono ventas tdc
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - billpocket
            - deposito spei
            - spei banorte
            la segunda línea deben contener:
            - pocket de latinoamerica sapi de cv
            - net pay sapi de cv
            la tercera línea deben contener:
            - deposito bpu y 10 numeros
            - bn-nts y 6 digitos

            algunas líneas pueden contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "santander": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - deposito ventas del dia afil
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - abono transferencia spei hora
            la segunda línea deben contener:
            - de la cuenta
            - recibido de stp
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "multiva": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - ventas tpvs 
            - venta tdd
            - venta tdc
            - ventas tarjetas
            - ventas tdc inter
            - ventas credito 
            - ventas debito
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - spei recibido stp
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "citibanamex": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - deposito ventas netas por evopaymx
            - deposito ventas netas
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - deposito ventas netas d tar
            - deposito ventas netas d amex
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "banamex": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción de una línea:
            - deposito ventas netas por evopaymx
            - deposito ventas netas
            - BN-NTS029220
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - deposito ventas netas d tar
            - deposito ventas netas d amex
            - deposito spei
            las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "azteca": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción multilinea:
            la primer línea puede contener:
            - transferencia spei a su favor
            - deposito spei
            las demás líneas pueden contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "inbursa": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - deposito spei
            alguna de las demás líneas deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "intercam": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - recepcion spei jp morgan
            - recepcion spei santander
            - recepcion spei banorte
            - deposito spei
            la última línea deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,

    "vepormas": """ 
    CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas:
        Reglas de la extracción multilinea, para que sea válida debe cumplir ambas:
            la primer línea debe contener:
            - recepcion spei jp morgan
            - recepcion spei santander
            - recepcion spei banorte
            - deposito spei
            la última línea deben contener:
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
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba, son tratados como 'generales'.
    """,
}