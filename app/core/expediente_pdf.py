"""PDF sin archivos públicos: datos actuales o copia conservada al cerrar."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def document_lines(data):
    p, company, supervisor = data["practica"], data["centro"], data["supervisor"]
    lines = [("title", "Expediente de prácticas"), ("body", "PrácticasCC · Ciencias de la Comunicación · UNSA"),
        ("body", "CERRADO · Versión 1" if data["cierre"] else "EN CURSO · Documento de seguimiento"),
        ("heading", "Datos de la práctica"), ("body", f"Practicante: {p['practicanteNombre']}"),
        ("body", f"Aula: {p['aulaNombre']} · Periodo: {p['periodo']}"), ("body", f"Docente: {p['docenteNombre']}"),
        ("body", f"Horas validadas: {p['horasValidadas']} / {p['horasMinimas']} h (mínimo configurado para esta práctica)."),
        ("body", f"Centro: {company['nombre']} · RUC: {company['ruc']}" if company else "Centro sin asociar."),
        ("body", f"Dirección: {company['direccion']}" if company else ""),
        ("body", f"Supervisor: {supervisor['nombre']} · {supervisor['cargo']}" if supervisor else "Supervisor sin asociar."),
        ("heading", "Requisitos de cierre")]
    for item in data["checklist"]:
        lines.append(("body", f"{'Cumplido' if item['cumplido'] else 'Pendiente'} · {item['titulo']}: {item['detalle']}"))
    config = data["configuracion"]
    if config:
        lines += [("body", f"Requisitos confirmados por {config['responsable']} el {config['fecha']}."),
            ("body", f"Nota mínima exigida: {config['notaMinima'] if config['notaMinima'] is not None else 'sin umbral numérico; se exige revisión docente'}."), ("body", config["motivo"])]
    lines.append(("heading", "Evaluación del supervisor"))
    assessment = data["evaluacion"]
    if assessment:
        lines += [("body", f"{assessment['supervisorNombre']} · {assessment['fecha']} · Revisión {assessment['revision']}"),
            ("body", f"Conclusión: {assessment['conclusion'].replace('_', ' ')}"),
            ("body", "Desempeño: " + assessment["desempeno"]), ("body", "Fortalezas: " + assessment["fortalezas"]),
            ("body", "Aspectos por mejorar: " + assessment["mejoras"]),
            ("body", "Conformidad registrada con cuenta SSP. No constituye firma digital.")]
    else:
        lines.append(("body", "Evaluación pendiente."))
    lines.append(("heading", "Tareas y retroalimentación"))
    for item in data["tareas"]:
        lines += [("body", f"{item['titulo']} · {'Exigida' if item['obligatoria'] else 'Consulta'} · Nota: {item['nota'] if item['nota'] is not None else 'sin calificar'}"),
            ("body", item["retroalimentacion"] or "Sin retroalimentación.")]
    if not data["tareas"]:
        lines.append(("body", "Sin tareas publicadas."))
    lines.append(("heading", "Metas de producción"))
    for item in data["metas"]:
        lines.append(("body", f"{item['tipo'].replace('_', ' ')} · {item['descripcion']} · {item['alcanzada']} / {item['objetivo']} · {'Exigida' if item['obligatoria'] else 'Consulta'}"))
    if not data["metas"]:
        lines.append(("body", "Sin metas registradas."))
    lines.append(("heading", "Bitácora de actividades"))
    for item in data["horas"]:
        lines += [("body", f"{item['fecha'][:10]} · {item['horas']} h · {item['estado']}"), ("body", item["descripcion"])]
        if item["observacion"]:
            lines.append(("body", "Observación: " + item["observacion"]))
    if not data["horas"]:
        lines.append(("body", "Sin actividades registradas."))
    lines.append(("heading", "Autorización de cierre"))
    closing = data["cierre"]
    if closing:
        lines += [("body", f"Responsable: {closing['responsable']} · {closing['fecha']}"), ("body", closing["motivo"]),
            ("body", "Copia de los datos al confirmar el cierre. Versión 1."), ("body", "Revisión confirmada: " + closing["revisionConfirmada"])]
    else:
        lines.append(("body", "Este documento no acredita el cierre de la práctica."))
    return lines


def render_pdf(data):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    for key in ("Title", "Heading2"):
        styles[key].textColor = colors.HexColor("#5E151D")
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 15
    mapping = {"title": styles["Title"], "heading": styles["Heading2"], "body": styles["BodyText"]}
    story = []
    for kind, text in document_lines(data):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), mapping[kind]))
        story.append(Spacer(1, 5))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#746D6A"))
        canvas.drawString(40, 25, "PrácticasCC · Documento de seguimiento")
        canvas.drawRightString(A4[0] - 40, 25, f"Página {doc.page}")
        canvas.restoreState()
    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=45,
        title="Expediente de prácticas · PrácticasCC", author="PrácticasCC").build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
