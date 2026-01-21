from .responses_general import ErrorRespuestaBase, ContribuyenteBaseFisica, ContribuyenteBaseMoral
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Self, Union

# ---- Modelo para el servicio de Constancia de Situación Fiscal (CSF) ----
class CSF:
    """Namespace para todos los modelos relacionados con la extración de CSF."""
    class ErrorRespuesta(ErrorRespuestaBase):
        """Error específico para el procesamiento de CSF."""
        pass

    class DatosIdentificacionPersonaFisica(ContribuyenteBaseFisica):
        """Datos de la sección 'Identificación del Contribuyente' en personas físicas."""
        nombre: Optional[str] = None
        primer_apellido: Optional[str] = None
        segundo_apellido: Optional[str] = None
        inicio_operaciones: Optional[str] = None
        estatus_padron: Optional[str] = None
        cambio_estado: Optional[str] = None
        nombre_comercial: Optional[str] = None

        @model_validator(mode='after')
        def calcular_nombre_comercial_si_falta(self) -> Self:
            # 1. Verificamos si nombre_comercial está vacío, es None, o son solo espacios
            if not self.nombre_comercial or not self.nombre_comercial.strip():
                
                # 2. Recolectamos las partes que sí tengan valor
                partes = [
                    valor 
                    for valor in (self.nombre, self.primer_apellido, self.segundo_apellido)
                    if valor and valor.strip() # Filtramos Nones y cadenas vacías
                ]
                
                # 3. Si hay partes, las unimos y asignamos
                if partes:
                    self.nombre_comercial = " ".join(partes)
            
            else:
                # Opcional: Si ya traía valor, le hacemos un strip por limpieza
                self.nombre_comercial = self.nombre_comercial.strip()
    
            return self

    class DatosIdentificacionPersonaMoral(ContribuyenteBaseMoral):
        """Datos de la sección 'Identificación del Contribuyente.' en personas morales."""
        inicio_operaciones: Optional[str] = None
        estatus_padron: Optional[str] = None
        cambio_estado: Optional[str] = None

    class DatosDomicilioRegistrado(BaseModel):
        """Datos de la sección 'Domicilio Registrado'"""
        codigo_postal: Optional[str] = None
        nombre_vialidad: Optional[str] = None
        nombre_localidad: Optional[str] = None
        entidad_federativa: Optional[str] = None
        vialidad: Optional[str] = None
        numero_interior: Optional[str] = None
        numero_exterior: Optional[str] = None
        colonia: Optional[str] = None
        municipio: Optional[str] = None
        calle: Optional[str] = None

        @field_validator('colonia', mode='before')
        @classmethod
        def normalizar_colonia(cls, v):
            if not v:
                return None

            texto = v.strip().lower()

            valores_invalidos = {
                "otra no especificada en el catálogo",
                "otra no especificada en el catalogo",
                "no aplica",
                "n/a",
            }

            if texto in valores_invalidos:
                return None  # o "" si prefieres

            return v.strip()

    class ActividadEconomica(BaseModel):
        """Datos de una de las actividades económicas listadas en el CSF"""
        orden: Optional[int] = None
        act_economica: Optional[str] = None
        porcentaje: Optional[float] = None
        fecha_inicio: Optional[str] = None
        fecha_final: Optional[str] = None

    class Regimen(BaseModel):
        """Datos de uno de los regímenes fiscales listados."""
        nombre_regimen: Optional[str] = None
        fecha_inicio: Optional[str] = None
        fecha_fin: Optional[str] = None

    class ResultadoConsolidado(BaseModel):
        """Modelo de respuesta final para el análisis de CSF exitóso."""
        tipo_persona: Optional[str] = None
        identificacion_contribuyente: Optional[Union["CSF.DatosIdentificacionPersonaFisica", "CSF.DatosIdentificacionPersonaMoral"]] = None
        domicilio_registrado: Optional["CSF.DatosDomicilioRegistrado"] = None
        actividad_economica: List["CSF.ActividadEconomica"] = Field(default_factory=list)
        regimen_fiscal: List["CSF.Regimen"] = Field(default_factory=list)
        error_lectura_csf: Optional[str] = None