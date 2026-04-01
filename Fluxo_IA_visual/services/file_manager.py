import shutil
import os
import uuid
import zipfile
import time
import logging
from pathlib import Path
from fastapi import UploadFile, HTTPException
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FileManagerService:
    def __init__(self, upload_dir: str = "temp_uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.TTL_SECONDS = 3600 # 1 Hora de vida

    def _limpiar_archivos_antiguos(self):
        """
        Limpia archivos y carpetas extraídas en temp_uploads que superen la hora de vida.
        """
        try:
            ahora = time.time()
            contador = 0
            
            # iterdir() lee todo lo que hay en la carpeta (archivos y subcarpetas)
            for ruta in self.upload_dir.iterdir():
                # Obtenemos la fecha de modificación
                tiempo_modificacion = ruta.stat().st_mtime
                
                if ahora - tiempo_modificacion > self.TTL_SECONDS:
                    if ruta.is_file():
                        ruta.unlink() # Borra archivo
                        contador += 1
                    elif ruta.is_dir():
                        shutil.rmtree(ruta) # Borra carpeta entera con su contenido
                        contador += 1
                        
            if contador > 0:
                logger.info(f"Limpieza FileManager: Se eliminaron {contador} temporales antiguos.")
        except Exception as e:
            logger.warning(f"Error limpiando temporales antiguos: {e}")

    def guardar_archivo_temporal(self, upload_file: UploadFile) -> Path:
        """
        Guarda el archivo subido en disco usando streaming para no saturar la RAM.
        Retorna la ruta absoluta del archivo guardado.
        """
        # Ejecutamos la limpieza silenciosa cada que suben un archivo nuevo
        self._limpiar_archivos_antiguos()
        
        try:
            # Generamos un nombre único para evitar colisiones
            file_extension = Path(upload_file.filename).suffix
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = self.upload_dir / unique_filename

            # Usamos shutil.copyfileobj para escribir en disco por chunks (buffer)
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
            
            return file_path
        except Exception as e:
            logger.error(f"Error guardando archivo temporal {upload_file.filename}: {e}")
            raise HTTPException(status_code=500, detail="Error interno al guardar el archivo.")
        finally:
            upload_file.file.close()

    def procesar_entrada(self, upload_file: UploadFile) -> List[Dict[str, Any]]:
        """
        Maneja la lógica de si es ZIP o PDF y retorna una lista de diccionarios
        con la ruta del archivo y su nombre original.
        """
        temp_path = self.guardar_archivo_temporal(upload_file)
        archivos_listos = []

        # Caso 1: Es un ZIP
        if str(temp_path).lower().endswith(".zip"):
            try:
                # --- PARÁMETROS DE SEGURIDAD (ANTI ZIP-BOMB) ---
                MAX_FILES_IN_ZIP = 50  # Máximo de PDFs permitidos por ZIP
                MAX_TOTAL_UNCOMPRESSED_MB = 100 # 100 MB máximo en total al extraer todo
                MAX_COMPRESSION_RATIO = 100 # Si se expande más de 100 veces su tamaño, es sospechoso
                
                max_bytes = MAX_TOTAL_UNCOMPRESSED_MB * 1024 * 1024
                
                extract_dir = self.upload_dir / f"extracted_{uuid.uuid4()}"
                extract_dir.mkdir(exist_ok=True)

                with zipfile.ZipFile(temp_path, "r") as zip_ref:
                    archivos_a_extraer = []
                    peso_total_descomprimido = 0
                    
                    # 1. Inspección de metadatos (Sin extraer nada todavía)
                    for info_archivo in zip_ref.infolist():
                        # Ignoramos carpetas y basura del sistema operativo
                        if info_archivo.is_dir() or info_archivo.filename.startswith("__MACOSX") or not info_archivo.filename.lower().endswith(".pdf"):
                            continue
                        
                        # A. Validar Ratio de Compresión (Prevención de bombas altamente comprimidas)
                        if info_archivo.compress_size > 0:
                            ratio = info_archivo.file_size / info_archivo.compress_size
                            if ratio > MAX_COMPRESSION_RATIO:
                                logger.critical(f"Alerta de Seguridad: Zip Bomb detectada. Ratio anormal: {ratio}:1")
                                raise HTTPException(status_code=400, detail="El archivo ZIP contiene datos sospechosos o está corrupto.")
                        
                        archivos_a_extraer.append(info_archivo.filename)
                        peso_total_descomprimido += info_archivo.file_size
                    
                    # B. Validar cantidad total de archivos
                    if len(archivos_a_extraer) > MAX_FILES_IN_ZIP:
                        logger.warning(f"ZIP rechazado: Contenía {len(archivos_a_extraer)} archivos.")
                        raise HTTPException(status_code=400, detail=f"El ZIP contiene demasiados archivos. El máximo es {MAX_FILES_IN_ZIP}.")
                    
                    # C. Validar peso total en disco
                    if peso_total_descomprimido > max_bytes:
                        logger.warning(f"ZIP rechazado: Peso inflado superaría {MAX_TOTAL_UNCOMPRESSED_MB}MB.")
                        raise HTTPException(status_code=413, detail="El contenido del ZIP es demasiado grande para procesarse.")

                    # 2. Si pasó todas las auditorías, procedemos a extraer
                    for member in archivos_a_extraer:
                        zip_ref.extract(member, path=extract_dir)
                        full_path = extract_dir / member
                        
                        archivos_listos.append({
                            "path": full_path,
                            "filename": Path(member).name,
                            "original_source": upload_file.filename,
                            "es_zip_content": True
                        })
                
                # Borrar el .zip original para ahorrar espacio
                os.remove(temp_path)

            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="El archivo ZIP está corrupto.")
            except HTTPException:
                # Si nosotros lanzamos el error de validación, limpiamos y lo dejamos subir al router
                os.remove(temp_path)
                raise
        
        # Caso 2: Es un PDF
        elif str(temp_path).lower().endswith(".pdf"):
            archivos_listos.append({
                "path": temp_path,
                "filename": upload_file.filename,
                "original_source": upload_file.filename,
                "es_zip_content": False
            })
        
        else:
            # Limpieza inmediata si no es válido
            os.remove(temp_path)
            logger.warning(f"Archivo ignorado: {upload_file.filename}")

        return archivos_listos

    def limpiar_temporales(self, rutas: List[Path]):
        """Elimina los archivos temporales de forma manual después de procesar."""
        for ruta in rutas:
            try:
                if ruta.exists():
                    os.remove(ruta)
                # Si es carpeta (del zip), intentar borrarla si está vacía
                if ruta.parent.name.startswith("extracted_"):
                    try:
                        os.rmdir(ruta.parent) 
                    except OSError:
                        pass # La carpeta no estaba vacía aún
            except Exception as e:
                logger.warning(f"No se pudo borrar temporal {ruta}: {e}")