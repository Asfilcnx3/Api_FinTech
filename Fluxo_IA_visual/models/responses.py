from typing import List, Optional, Self, Union
from pydantic import BaseModel, Field, field_validator, model_validator

class RespuestaProcesamientoIniciado(BaseModel):
    mensaje: str
    job_id: str
    estatus: str
    
# ---- Modelos base reutilizables ----
class ErrorRespuestaBase(BaseModel):
    """Modelo base para respuestas de error estandarizadas."""
    error: str

class ContribuyenteBaseFisica(BaseModel):
    """Modelo base para la identificación del contribuyente (RFC y CURP)."""
    rfc: Optional[str] = None
    curp: Optional[str] = None

class ContribuyenteBaseMoral(BaseModel):
    """Modelo base para la identificación del contribuyente moral."""
    rfc: Optional[str] = None
    razon_social: Optional[str] = None
    regimen_capital: Optional[str] = None
    nombre_comercial: Optional[str] = None

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

# ----- Clases para respuestas de Análisis TPV (Fluxo) -----
class AnalisisTPV:
    """Namespace para todos los modelos relacionados con el analisis de cuenta TPV."""
    class ErrorRespuesta(ErrorRespuestaBase):
        """Error específico para el procesamiento de TPV."""
        pass

    class Transaccion(BaseModel):
        """Representa una única transaccion encontrada dentro del documento [3 partes]."""
        fecha: str
        descripcion: str
        monto: str
        tipo: str
        categoria: str
    
    class ResultadoTPV(BaseModel):
        """Representa todas las transacciones TPV encontadas dentro del documento."""
        transacciones: List["AnalisisTPV.Transaccion"] = Field(default_factory=list)
        error_transacciones: Optional[str] = None

    class ResultadoAnalisisIA(BaseModel):
        """Clase de respuesta para un analisis de carátula exitóso."""
        banco: str
        tipo_moneda: Optional[str] = None
        rfc: Optional[str] = None
        nombre_cliente: Optional[str] = None
        clabe_interbancaria: Optional[str] = None
        periodo_inicio: Optional[str] = None
        periodo_fin: Optional[str] = None
        comisiones: Optional[float] = None
        depositos: Optional[float] = None
        cargos: Optional[float] = None
        saldo_promedio: Optional[float] = None
        depositos_en_efectivo: Optional[float] = None
        traspaso_entre_cuentas: Optional[float] = None
        total_entradas_financiamiento: Optional[float] = None
        entradas_bmrcash: Optional[float] = None
        total_moratorios: Optional[float] = None
        entradas_TPV_bruto: Optional[float] = None
        entradas_TPV_neto: Optional[float] = None

    class ResultadoExtraccion(BaseModel):
        """Representa la respuesta para los documentos individuales -> Caratula + Resultados TPV."""
        AnalisisIA: Optional["AnalisisTPV.ResultadoAnalisisIA"] = None
        DetalleTransacciones: Optional[Union["AnalisisTPV.ResultadoTPV", "AnalisisTPV.ErrorRespuesta"]] = None

    class ResultadoTotal(BaseModel):
        """Representa una respuesta exitosa de todos los lotes analizados."""
        total_depositos: Optional[float] = None # Representa lógica interna
        es_mayor_a_250: Optional[bool] = None # Representa logica interna
        resultados_generales: List["AnalisisTPV.ResultadoAnalisisIA"] # -> Representa únicamente la caratula del estado de cuenta
        resultados_individuales: List["AnalisisTPV.ResultadoExtraccion"] # - > Representa el analisis completo (caratula + tpv)

# ----- Clases para respuestas de NomiFlash -----
class NomiFlash:
    """Namespace para todos los modelos relacionados con el procesamiento de nóminas."""
    class ErrorRespuesta(ErrorRespuestaBase):
        """Error específico para el procesamiento de NomiFlash."""
        pass
    
    class RespuestaNomina(ContribuyenteBaseFisica):
        """Datos extraidos del análisis del recibo de Nómina."""
        datos_qr: Optional[str] = None
        nombre: Optional[str] = None
        apellido_paterno: Optional[str] = None
        apellido_materno: Optional[str] = None
        dependencia: Optional[str] = None
        secretaria: Optional[str] = None
        numero_empleado: Optional[str] = None
        puesto_cargo: Optional[str] = None
        categoria: Optional[str] = None
        total_percepciones: Optional[float] = None
        total_deducciones: Optional[float] = None
        salario_neto: Optional[float] = None
        periodo_inicio: Optional[str] = None
        periodo_fin: Optional[str] = None
        fecha_pago: Optional[str] = None
        periodicidad: Optional[str] = None
        error_lectura_nomina: Optional[str] = None
    
    class SegundaRespuestaNomina(ContribuyenteBaseFisica):
        datos_qr: Optional[str] = None
        nombre: Optional[str] = None
        error_lectura_nomina: Optional[str] = None

    class RespuestaEstado(BaseModel):
        """Datos extraidos del análisis del Estado de Cuenta."""
        datos_qr: Optional[str] = None
        clabe: Optional[str] = None
        nombre_usuario: Optional[str] = None
        rfc: Optional[str] = None
        numero_cuenta: Optional[str] = None
        error_lectura_estado: Optional[str] = None

    # Respuesta para respuesta de analisis de Comprobantes de Domicilio
    class RespuestaComprobante(BaseModel):
        """Datos extraidos del análisis del Comprobante de Domicilio."""
        domicilio: Optional[str] = None
        inicio_periodo: Optional[str] = None
        fin_periodo: Optional[str] = None
        error_lectura_comprobante: Optional[str] = None

    # Respuesta para respuesta total (Las respuestas de los resultados finales)
    class ResultadoConsolidado(BaseModel):
        """Representa la respuesta exitosa del analisis de estados de cuenta final."""
        Nomina: Optional["NomiFlash.RespuestaNomina"] = None
        SegundaNomina: Optional["NomiFlash.SegundaRespuestaNomina"] = None
        Estado: Optional["NomiFlash.RespuestaEstado"] = None
        Comprobante: Optional["NomiFlash.RespuestaComprobante"] = None
        es_menor_a_3_meses: Optional[bool] = None   # -> Representa lógica interna
        el_rfc_es_igual: Optional[bool] = None      # -> Representa lógica interna
        el_qr_es_igual: Optional[bool] = None       # -> Representa lógica interna