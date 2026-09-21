import hashlib
import io
import json
from pathlib import Path
import reportlab
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
import os
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from .audit import canonical, verify
from .prompt_loop import PromptLoopEngine

def retained_observations(events):
    """Unique observations for the report, with legacy sample-only fallback.

    New signed signal events take precedence over periodic snapshots. The
    JSON audit retains every occurrence, revision and resolution separately.
    """
    signals = {}
    for event in events:
        if event["kind"] == "sample":
            for result in event["data"]["results"]:
                for signal in result["signals"]:
                    signals[signal["id"]] = signal.copy()
    for event in events:
        if event["kind"] == "signal_observed":
            signal = event["data"]["signal"].copy()
            previous = signals.get(signal["id"], {})
            signal["first_observed_at"] = previous.get("first_observed_at", event["time"])
            signal["last_observed_event_at"] = event["time"]
            signals[signal["id"]] = signal
    return signals


def _register_fonts():
    windir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows") / "Fonts"
    candidates = [
        # Windows system fonts
        (str(windir / "segoeui.ttf"), str(windir / "segoeuib.ttf")),
        (str(windir / "arial.ttf"), str(windir / "arialbd.ttf")),
        # macOS system fonts
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
        # Linux system fonts
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont('IIMSans', regular))
                pdfmetrics.registerFont(TTFont('IIMSansBold', bold))
                registerFontFamily('IIMSans', normal='IIMSans', bold='IIMSansBold')
                return True
            except Exception:
                continue
    # Fallback to Vera bundled with ReportLab
    font_directory = Path(reportlab.__file__).parent / 'fonts'
    pdfmetrics.registerFont(TTFont('IIMSans', str(font_directory / 'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('IIMSansBold', str(font_directory / 'VeraBd.ttf')))
    registerFontFamily('IIMSans', normal='IIMSans', bold='IIMSansBold')
    return False

UNICODE_FONT_AVAILABLE = _register_fonts()


def generate_qr_svg(payload: str) -> str:
    from reportlab.graphics.barcode import qr
    widget = qr.QrCodeWidget(payload)
    widget.getBounds()
    modules = widget.qr.modules
    count = widget.qr.getModuleCount()
    path_d = []
    for r in range(count):
        for c in range(count):
            if modules[r][c]:
                path_d.append(f"M{c+4},{r+4}h1v1h-1z")
    svg_size = count + 8
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_size} {svg_size}" '
            f'shape-rendering="crispEdges" width="100%" height="100%">'
            f'<rect width="{svg_size}" height="{svg_size}" fill="#ffffff"/>'
            f'<path d="{"".join(path_d)}" fill="#0c171c"/></svg>')


def render_report(bundle, synthetic=False, prompt_loop_summary=None):
    if not verify(bundle):
        raise ValueError("Cannot generate a report from an invalid audit bundle")
    stream = io.BytesIO()
    styles = {
        "title": ParagraphStyle("title",fontName="IIMSans",fontSize=25,leading=31,textColor=colors.HexColor('#122c36'),spaceAfter=10),
        "h": ParagraphStyle("heading",fontName="IIMSansBold",fontSize=12,leading=17,textColor=colors.HexColor('#173f45'),spaceBefore=16,spaceAfter=7,keepWithNext=True),
        "p": ParagraphStyle("body",fontName="IIMSans",fontSize=9,leading=14,textColor=colors.HexColor('#344651'),spaceAfter=7),
        "small": ParagraphStyle("small",fontName="IIMSans",fontSize=7.4,leading=11,textColor=colors.HexColor('#526976'),spaceAfter=5),
    }
    def p(text,style="p"):
        text = str(text)
        if not UNICODE_FONT_AVAILABLE:
            text = text.encode('ascii', 'backslashreplace').decode()
        return Paragraph(escape(text),styles[style])
    manifest = bundle["manifest"]
    session = manifest["session"]
    events = [json.loads(e["payload_json"]) for e in bundle["events"]]
    samples = [e["data"] for e in events if e["kind"] == "sample"]
    latest = samples[-1] if samples else {"score":{"value":None,"coverage":0},"results":[]}
    signals = retained_observations(events)
    story = [p("INTERVIEW INTEGRITY / SESSION RECORD","small"),p("Interview integrity report","title")]
    if synthetic:
        story.append(p("SYNTHETIC SAMPLE - not a real candidate or device observation","h"))
    story += [p("Observations for human review. This report does not determine cheating, honesty, competence or hiring eligibility."),
              p(f"Session {session['id']} | Status: {session['status']}","small"),
              p(f"Started: {session['created_at']} | Ended: {session.get('ended_at') or 'Still active'}","small")]
    session_context = {
        "consent": session.get("consent", {}),
        "signals": list(signals.values()),
        "notes": [e["data"].get("detail") for e in events if e.get("kind") == "timeline" and isinstance(e.get("data"), dict) and "detail" in e["data"]],
    }
    summary_data = prompt_loop_summary or PromptLoopEngine().run(session_context)
    story += [
        p("Session summary", "h"),
        p(summary_data["summary"]),
        p("Summary method: " + ("local deterministic summary" if summary_data.get("method") == "deterministic" else "configured summary provider; human review required"), "small"),
    ]
    value=latest["score"]["value"]
    badge_label = {
        "STANDARD_BASELINE": "Standard Baseline",
        "OBSERVATIONS_FOR_REVIEW": "Review Recommended",
        "PARTIAL_COVERAGE": "Partial Coverage",
        "INSUFFICIENT_COVERAGE": "Insufficient Coverage",
    }.get(latest["score"].get("badge"), "Baseline")
    overview=[[p("STATUS CATEGORY","small"),p("TECHNICAL INDEX","small"),p("COVERAGE","small"),p("OBSERVATIONS","small")],
              [p(badge_label,"h"),p(f"{value if value is not None else 'N/A'} / 100","h"),p(f"{latest['score']['coverage']}%","h"),p(str(len(signals)),"h")]]
    table=Table(overview,colWidths=[44*mm,44*mm,43*mm,43*mm])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#edf5f3')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#bdd5cf')),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story += [Spacer(1,10),table,p("The index is an uncalibrated technical heuristic, not a misconduct probability. Missing checks are unknown. Eye position and answer timing never change the index.","small"),p("Candidate choices and privacy","h")]
    selected=[key for key,value in session["consent"].items() if value is True and key in ('processes','windows','displays','audio_devices','extensions','gaze')]
    story += [p("Selected scopes: "+", ".join(selected)),p("No keystrokes, passwords, desktop images, browser history, microphone audio or system audio were recorded. The optional pre-flight preview may open a local microphone level meter and camera preview; none of that preview data is saved or sent to the worker. Session camera frames are discarded locally; retained camera metadata can include eye-position consistency, quality/calibration statistics, lighting, face count and multiple-face observations. Matching metadata, aggregates and candidate notes are retained in the local session log for 24 hours; exported copies have their own retention.")]
    story.append(p("Recorded disclosure version: " + session["consent"].get("version", "legacy / unspecified"), "small"))
    story.append(p("Detector coverage at the final available sample","h"))
    if latest["results"]:
        rows=[[p("DETECTOR","small"),p("STATUS / LIMITATION","small")]]
        for r in latest["results"]:
            rows.append([p(r["detector"],"small"),p(r["status"]+" - "+r["detail"],"small")])
        table=Table(rows,colWidths=[56*mm,118*mm],repeatRows=1,hAlign=TA_LEFT)
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dce5e8')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(table)
    else: story.append(p("No detector samples were retained. Do not interpret this as a clean result."))
    observation_heading = p("Observations and alternative explanations","h")
    if not signals:
        story.append(KeepTogether([observation_heading,p("No matching observations were retained in the signed record.")]))
    for index, s in enumerate(signals.values()):
        block=[p(s["title"],"h"),p(s["explanation"]),p("Evidence: "+canonical(s["evidence"]),"small"),p(f"Observation confidence: {round(s['confidence']*100)}% (heuristic, not validated).","small"),p("Alternative explanation / limitation: "+s["limitation"])]
        if s.get("first_observed_at"):
            block.append(p("First observed: " + s["first_observed_at"] +
                           " | Latest observation event: " + s["last_observed_event_at"], "small"))
        if index == 0:
            block.insert(0,observation_heading)
        story.append(KeepTogether(block))
    story.append(p("Candidate context and timeline","h"))
    for event in events:
        if event["kind"]=="timeline":
            data=event["data"]
            story.append(p(f"{data['time']} | {data['title']} - {data['detail']}","small"))
        elif event["kind"] in ("stopped","interrupted"):
            story.append(p(f"{event['time']} | {event['kind']} - {event['data']['reason']}","small"))
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing, Group
    attest_payload = canonical({"id": session["id"], "pk": bundle["public_key"], "head": manifest["head"]})
    qr_widget = qr.QrCodeWidget(attest_payload)
    bounds = qr_widget.getBounds()
    bw = bounds[2] - bounds[0]
    bh = bounds[3] - bounds[1]
    qr_size = 28 * mm
    qr_drawing = Drawing(qr_size, qr_size)
    qr_group = Group()
    qr_group.translate(-bounds[0], -bounds[1])
    qr_group.scale(qr_size / bw, qr_size / bh)
    qr_group.add(qr_widget)
    qr_drawing.add(qr_group)

    audit_text = [
        p("Audit verification", "h"),
        p(f"{manifest['event_count']} chained events. Stored Ed25519 checkpoint verified before rendering."),
        p("Chain head: " + manifest["head"], "small"),
        p("Public key: " + bundle["public_key"], "small"),
        p("Bundle SHA-256: " + hashlib.sha256(canonical(bundle).encode()).hexdigest(), "small"),
    ]
    audit_table = Table([[audit_text, qr_drawing]], colWidths=[140 * mm, 34 * mm])
    audit_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story += [
        KeepTogether([
            audit_table,
            p("Keep the signed JSON export for verification. The PDF is a human-readable rendering, not a digitally signed PDF. A public key must be pinned independently to authenticate its source; a candidate-controlled device is not a trusted attestation environment.", "small"),
            p("Reading-like movements, hidden GPU overlays, AI speech identification and concealed hardware are not established by this report. Compare the evidence with agreed interview rules and candidate explanations. No automatic hiring decisions are supported.", "small"),
            p("Report text preserves Unicode; the signed JSON provides the canonical audit log." if UNICODE_FONT_AVAILABLE else "Non-ASCII text may be displayed as Unicode escape sequences; the signed JSON preserves the original text.", "small"),
        ])
    ]
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#dce5e8'));canvas.line(18*mm,17*mm,192*mm,17*mm)
        canvas.setFont('IIMSans',7);canvas.setFillColor(colors.HexColor('#687d88'))
        canvas.drawString(18*mm,12*mm,'INTERVIEW INTEGRITY MONITOR / DEVELOPER PREVIEW / HUMAN REVIEW REQUIRED')
        canvas.drawRightString(192*mm,12*mm,str(doc.page))
    doc=SimpleDocTemplate(stream,pagesize=(210*mm,297*mm),rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=24*mm,title="Interview Integrity Report",author="Interview Integrity Monitor")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
