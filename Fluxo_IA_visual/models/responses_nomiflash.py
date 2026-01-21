from .responses_general import ErrorRespuestaBase, ContribuyenteBaseFisica
from pydantic import BaseModel
from typing import Optional

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