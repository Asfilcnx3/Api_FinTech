import asyncio
import logging
import re
import fitz
from pathlib import Path
from datetime import datetime

# Ajusta las rutas relativas según la ubicación exacta de tu carpeta services
from ..core.motor_caratulas_light import procesar_caratula_frontend
from ..core.motor_caratulas import MotorCaratulas
from ..core.config import Settings
from .file_manager import FileManagerService
from .storage_service import StorageService

logger = logging.getLogger(__name__)

class CaratulasLightService:
    """
    Servicio encargado de orquestar la extracción concurrente de carátulas ligeras.
    Mantiene el router limpio delegando aquí la lógica de negocio pesada.
    """
    def __init__(
        self,
        settings: Settings,
        motor_base: MotorCaratulas,
        file_manager: FileManagerService,
        storage: StorageService
    ):
        self.settings = settings
        self.motor_base = motor_base
        self.file_manager = file_manager
        self.storage = storage
    
    def _evaluar_viabilidad_documento(self, pdf_bytes: bytes, nombre_archivo: str) -> dict:
        """
        Gatekeeper inteligente: Evalúa si vale la pena enviar el PDF a la IA.
        Retorna un dict con {"viable": bool, "razon": str}
        """
        texto_global = ""
        tiene_imagenes = False
        
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                paginas_a_revisar = min(3, len(doc))
                for i in range(paginas_a_revisar):
                    pagina = doc[i]
                    texto_global += pagina.get_text("text").lower() + "\n"
                    if pagina.get_images(full=True):
                        tiene_imagenes = True
        except Exception as e:
            logger.warning(f"No se pudo pre-evaluar el PDF {nombre_archivo}: {e}")
            return {"viable": False, "razon": "PDF corrupto o ilegible."}

        nombre_limpio = nombre_archivo.lower()
        texto_limpio = texto_global.strip()
        
        # ==========================================================
        # 1. LISTA NEGRA: VETO INMEDIATO (El asesino de CSF y Nóminas)
        # ==========================================================
        palabras_veto_texto = [
            "constancia de situación fiscal", 
            "cédula de identificación fiscal",
            "comprobante fiscal digital",
            "recibo de nómina",
            "comisión federal de electricidad"
        ]
        palabras_veto_nombre = ["csf", "nomi", "factura", "recibo"]
        
        if any(veto in texto_limpio for veto in palabras_veto_texto) or any(veto in nombre_limpio for veto in palabras_veto_nombre):
            logger.info(f"[Gatekeeper] VETO APLICADO a: {nombre_archivo}")
            return {"viable": False, "razon": "Documento vetado (Detectado como CSF, Nómina o Factura)."}

        # ==========================================================
        # 2. SISTEMA DE PUNTOS
        # ==========================================================
        score = 0
        
        # A. Bono de Confianza por Nombre de Archivo (+40 pts)
        bancos_conocidos = ["hsbc", "banamex", "bbva", "banorte", "santander", "scotiabank", "bajio", "inbursa", "regio", "azteca"]
        if any(b in nombre_limpio for b in bancos_conocidos) or "edo" in nombre_limpio or "cta" in nombre_limpio:
            score += 40

        # B. Detección de Texto Basura (Mojibake)
        # Contamos cuántos caracteres son letras normales, números o espacios (ASCII básico)
        caracteres_normales = sum(1 for c in texto_limpio if c.isascii() and (c.isalnum() or c.isspace()))
        ratio_normalidad = caracteres_normales / len(texto_limpio) if len(texto_limpio) > 0 else 0
        
        # Es texto real si tiene más de 50 chars Y al menos el 40% son caracteres legibles
        es_texto_real = len(texto_limpio) > 50 and ratio_normalidad > 0.4

        # C. Evaluación de Texto (Solo si es texto real y legible)
        if es_texto_real:
            # Palabras clave financieras
            if self.motor_base.palabras_clave_regex.search(texto_limpio):
                score += 30
                
            # Datos Duros (RFC o CLABE)
            patron_rfc = r"[a-zñ&]{3,4}\d{6}[a-z0-9]{3}"
            patron_clabe = r"\b\d{18}\b"
            if re.search(patron_rfc, texto_limpio) or re.search(patron_clabe, texto_limpio):
                score += 30
                
            # Identidad del Banco
            match_banco = self.motor_base.banco_detection_regex.search(texto_limpio)
            if match_banco and self.motor_base.alias_banco_map.get(match_banco.group(0)):
                score += 30
                
        else:
            # CASO ESPECIAL: PDF de Puras Imágenes o TEXTO BASURA
            # Si el texto es ilegible o muy corto, pero tiene imágenes y el nombre sugiere que es un banco, pasa.
            if tiene_imagenes and score >= 40:
                logger.info(f"[Gatekeeper] Salvado por Caso Especial (Imagen/Basura): {nombre_archivo} | Ratio normalidad: {ratio_normalidad:.2f}")
                return {"viable": True, "razon": "PDF de imágenes/texto basura aprobado por nombre de archivo."}

        # ==========================================================
        # 3. VEREDICTO FINAL Y ENRUTAMIENTO (ROUTING)
        # ==========================================================
        UMBRAL_APROBACION = 50
        
        # Si NO pasó el umbral y tampoco es el caso especial de puras imágenes
        if score < UMBRAL_APROBACION and not (tiene_imagenes and score >= 40):
            logger.debug(f"[Gatekeeper] Rechazado {nombre_archivo} | Score: {score} | Ratio Normalidad: {ratio_normalidad:.2f}")
            return {"viable": False, "razon": f"Rechazado (Score: {score}/100). No parece un estado de cuenta válido."}

        # Si llegó hasta aquí, ES VIABLE. Ahora decidimos el enrutamiento:
        # Si es texto real (legible y suficiente), usamos el LLM de texto (Barato).
        # Si es Mojibake o puras imágenes, usamos Visión (Caro).
        requiere_vision = not es_texto_real
        
        razon = f"Aprobado con {score} puntos." if es_texto_real else "Aprobado por Caso Especial (Imagen/Basura)."
        
        return {
            "viable": True, 
            "requiere_vision": requiere_vision, 
            "razon": razon
        }
    
    def _obtener_sets_de_meses_requeridos(self) -> tuple:
        """
        Retorna dos sets con los periodos MM-YYYY obligatorios.
        Opción A: Los últimos 3 meses cerrados (ej. en Abril: Enero, Febrero, Marzo)
        Opción B: Los 3 meses asumiendo un mes de desfase (ej. en Abril: Diciembre, Enero, Febrero)
        """
        hoy = datetime.now()
        
        def calcular_mes_anio(meses_atras):
            mes = hoy.month - meses_atras
            anio = hoy.year
            while mes <= 0:
                mes += 12
                anio -= 1
            return f"{mes:02d}-{anio}"

        # Set A: Mes actual -1, -2, -3
        set_a = {calcular_mes_anio(1), calcular_mes_anio(2), calcular_mes_anio(3)}
        # Set B: Mes actual -2, -3, -4
        set_b = {calcular_mes_anio(2), calcular_mes_anio(3), calcular_mes_anio(4)}
        
        return set_a, set_b

    async def _procesar_archivo_individual(self, info_archivo: dict, semaforo: asyncio.Semaphore) -> dict:
        """Método privado: Procesa un solo archivo respetando el límite del semáforo."""
        async with semaforo:
            ruta_pdf = Path(info_archivo["path"])
            nombre_original = info_archivo["filename"]
            
            try:
                # A. Validar límite de peso
                tamanio_archivo = ruta_pdf.stat().st_size
                if tamanio_archivo > self.settings.max_file_size_bytes:
                    return {"error": {
                        "nombre_documento": nombre_original, 
                        "estatus_documento": "fallido", 
                        "detalle_error": f"Supera límite de {self.settings.MAX_FILE_SIZE_MB}MB."
                    }}

                # B. Leer de disco y validar Magic Bytes
                with open(ruta_pdf, "rb") as f:
                    magic_bytes = f.read(5)
                    if magic_bytes != b"%PDF-":
                        return {"error": {
                            "nombre_documento": nombre_original,
                            "estatus_documento": "fallido",
                            "detalle_error": "Firma de archivo inválida (no es PDF)."
                        }}
                    
                    f.seek(0)
                    pdf_bytes = f.read()
                
                # C. Evaluación de viabilidad inteligente (gatekeeper de costos)
                evaluacion = self._evaluar_viabilidad_documento(pdf_bytes, nombre_original)
                if not evaluacion["viable"]:
                    return {"error": {
                        "nombre_documento": nombre_original,
                        "estatus_documento": "fallido",
                        "detalle_error": evaluacion["razon"]
                    }}
                
                # Le pasamos la instrucción al motor de si debe usar Visión o Texto
                requiere_vision_flag = evaluacion.get("requiere_vision", True)

                # D. Extracción real con el motor ligero
                res_estructurada = await procesar_caratula_frontend(
                    pdf_bytes=pdf_bytes, 
                    motor_base=self.motor_base,
                    requiere_vision=requiere_vision_flag
                )

                # E. Evaluar resultado
                if res_estructurada.error_procesamiento:
                    return {"error": {
                        "nombre_documento": nombre_original,
                        "estatus_documento": "fallido",
                        "detalle_error": res_estructurada.error_procesamiento
                    }}
                
                # Convertimos el modelo Pydantic a diccionario e inyectamos los nuevos campos
                resultados_dict = []
                for item in res_estructurada.resultados:
                    dict_item = item.model_dump()
                    dict_item["nombre_documento"] = nombre_original
                    dict_item["estatus_documento"] = "exitoso"
                    resultados_dict.append(dict_item)
                    
                return {"exito": resultados_dict}
                
            except Exception as e:
                logger.error(f"Error procesando {nombre_original}: {str(e)}")
                return {"error": {
                    "nombre_documento": nombre_original,
                    "estatus_documento": "fallido",
                    "detalle_error": f"Error interno al extraer - {str(e)}"
                }}

    async def ejecutar_pipeline_concurrente(self, job_id: str, lista_archivos: list):
        """Orquestador background: Dispara N archivos a la vez, guardando estado en disco (JSON)."""
        try:
            self.storage.update_job(job_id, {
                "estatus": "procesando", 
                "resultados_exitosos": [], 
                "errores": []
            })
            
            semaforo = asyncio.Semaphore(15)
            
            tareas = [
                self._procesar_archivo_individual(info, semaforo)
                for info in lista_archivos
            ]
            
            resultados_brutos = await asyncio.gather(*tareas)
            
            exitos = []
            errores = []
            
            for res in resultados_brutos:
                if "error" in res:
                    errores.append(res["error"])
                elif "exito" in res:
                    exitos.extend(res["exito"])
            
            # ==========================================================
            # --- IDEA 1: INDICADOR ESTRICTO Y ALERTA DE PERIODOS ---
            # ==========================================================
            set_a, set_b = self._obtener_sets_de_meses_requeridos()
            
            # Extraemos todos los periodos encontrados en los PDFs
            periodos_encontrados = set(caratula.get("periodo") for caratula in exitos if caratula.get("periodo"))
            
            # El booleano será True SOLO SI el Set A completo o el Set B completo están
            tiene_caratulas_recientes = set_a.issubset(periodos_encontrados) or set_b.issubset(periodos_encontrados)
            
            mensaje_periodos = "Se encontraron los 3 meses requeridos."
            if not tiene_caratulas_recientes:
                faltantes_a = sorted(list(set_a - periodos_encontrados))
                faltantes_b = sorted(list(set_b - periodos_encontrados))
                
                # Elegimos el set que le exija al usuario subir MENOS archivos
                mejor_opcion = faltantes_a if len(faltantes_a) <= len(faltantes_b) else faltantes_b
                cantidad_faltante = len(mejor_opcion)
                
                # Diccionario para formatear los meses al español
                nombres_meses = {
                    "01": "enero", "02": "febrero", "03": "marzo", "04": "abril",
                    "05": "mayo", "06": "junio", "07": "julio", "08": "agosto",
                    "09": "septiembre", "10": "octubre", "11": "noviembre", "12": "diciembre"
                }
                
                meses_formateados = []
                for periodo in mejor_opcion:
                    mes_num, anio = periodo.split("-")
                    meses_formateados.append(f"{nombres_meses[mes_num]} {anio}")
                
                mensaje_periodos = f"Faltan al menos {cantidad_faltante} estado(s) de cuenta de los meses: {', '.join(meses_formateados)}"
                
                # Log explícito para saber qué pedía cada set y qué se le mostró al usuario
                logger.info(f"[Job {job_id}] Periodos incompletos. Faltantes Set A: {faltantes_a} | Faltantes Set B: {faltantes_b} | Mostrado al usuario: {meses_formateados}")
                    
            # ==========================================================
            # --- IDEA 2: VALIDACIÓN DE CONGRUENCIA (RFC / NOMBRE) ---
            # ==========================================================
            alerta_identidad = None
            if exitos:
                # Extraemos los RFCs y Nombres (ignorando nulos o vacíos)
                rfcs_detectados = set(c.get("rfc") for c in exitos if c.get("rfc"))
                nombres_detectados = set(c.get("nombre_cliente") for c in exitos if c.get("nombre_cliente"))
                
                incongruencia_rfc = len(rfcs_detectados) > 1
                incongruencia_nombre = len(nombres_detectados) > 1
                
                if incongruencia_rfc or incongruencia_nombre:
                    alerta_identidad = "Se detectaron estados de cuenta que podrían pertenecer a distintos titulares. "
                    detalles = []
                    if incongruencia_rfc: 
                        detalles.append(f"Múltiples RFCs: {', '.join(rfcs_detectados)}")
                    if incongruencia_nombre: 
                        detalles.append(f"Múltiples Nombres: {' | '.join(nombres_detectados)}")
                    alerta_identidad += f"[{' y '.join(detalles)}]"

            # ==========================================================
            # ACTUALIZACIÓN DEL JOB
            # ==========================================================
            self.storage.update_job(job_id, {
                "estatus": "completado",
                "indicador_caratulas_recientes": tiene_caratulas_recientes,
                "mensaje_periodos": mensaje_periodos, # <--- Se inyecta Idea 1
                "alerta_identidad": alerta_identidad, # <--- Se inyecta Idea 2
                "resultados_exitosos": exitos,
                "errores": errores
            })
            logger.info(f"Job {job_id} completado. {len(exitos)} éxitos, {len(errores)} errores.")

        except Exception as e:
            logger.error(f"Falla fatal en Job {job_id}: {e}")
            self.storage.update_job(job_id, {"estatus": "error", "detalle_error": str(e)})

        finally:
            rutas_a_borrar = [Path(info["path"]) for info in lista_archivos]
            self.file_manager.limpiar_temporales(rutas_a_borrar)