import shutil
import os
import uuid
import zipfile
import logging
from pathlib import Path
from fastapi import UploadFile, HTTPException
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FileManagerService:
    def __init__(self, upload_dir: str = "temp_uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def guardar_archivo_temporal(self, upload_file: UploadFile) -> Path:
        """
        Guarda el archivo subido en disco usando streaming para no saturar la RAM.
        Retorna la ruta absoluta del archivo guardado.
        """
        try:
            # Generamos un nombre único para evitar colisiones
            file_extension = Path(upload_file.filename).suffix
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = self.upload_dir / unique_filename

            # Usamos shutil.copyfileobj para escribir en disco por chunks (buffer)
            # Esto evita cargar el archivo entero en memoria.
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
        Estructura de retorno: [{'path': Path, 'filename': str, 'original_source': str}]
        """
        temp_path = self.guardar_archivo_temporal(upload_file)
        archivos_listos = []

        # Caso 1: Es un ZIP
        if str(temp_path).lower().endswith(".zip"):
            try:
                # Extraemos en una subcarpeta única para este ZIP
                extract_dir = self.upload_dir / f"extracted_{uuid.uuid4()}"
                extract_dir.mkdir(exist_ok=True)

                with zipfile.ZipFile(temp_path, "r") as zip_ref:
                    # Filtramos archivos basura (__MACOSX, etc) antes de extraer
                    files_to_extract = [
                        f for f in zip_ref.namelist() 
                        if f.lower().endswith(".pdf") and not f.startswith("__MACOSX")
                    ]
                    
                    for member in files_to_extract:
                        # zipfile.extract permite extraer directo a disco
                        zip_ref.extract(member, path=extract_dir)
                        full_path = extract_dir / member
                        
                        archivos_listos.append({
                            "path": full_path,
                            "filename": Path(member).name,
                            "original_source": upload_file.filename,
                            "es_zip_content": True
                        })
                
                # Opcional: Borrar el .zip original para ahorrar espacio, ya extrajimos lo útil
                os.remove(temp_path)

            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="El archivo ZIP está corrupto.")
        
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
            # Podrías lanzar error o simplemente ignorarlo (como hacías antes)
            logger.warning(f"Archivo ignorado: {upload_file.filename}")

        return archivos_listos

    def limpiar_temporales(self, rutas: List[Path]):
        """Elimina los archivos temporales después de procesar."""
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