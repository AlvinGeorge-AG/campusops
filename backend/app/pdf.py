from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.colors import HexColor
import io
import os

def _build_pdf(text: str, title: str = "") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.6*inch, bottomMargin=0.6*inch, leftMargin=0.8*inch, rightMargin=0.8*inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=14, alignment=TA_CENTER, spaceAfter=6, textColor=HexColor(0x1a1a1a))
    heading_style = ParagraphStyle('Heading', parent=styles['Normal'], fontSize=10, alignment=TA_RIGHT, spaceAfter=2)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, alignment=TA_JUSTIFY, leading=14, spaceAfter=6)
    subject_style = ParagraphStyle('Subject', parent=styles['Normal'], fontSize=10, alignment=TA_JUSTIFY, leading=14, spaceAfter=8, textColor=HexColor(0x222222))
    sign_style = ParagraphStyle('Sign', parent=styles['Normal'], fontSize=10, alignment=TA_JUSTIFY, leading=14, spaceAfter=2)
    story = []
    if title:
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.15*inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor(0xcccccc)))
        story.append(Spacer(1, 0.15*inch))
    # Preserve line breaks - split by lines and make paragraphs
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.08*inch))
            continue
        # Detect headers like "To," or "Subject:" or "Respected"
        if line.startswith("To,") or line.startswith("The Principal") or line.startswith("Govt."):
            style = heading_style if "To," in line else body_style
            if line.startswith("To,"):
                style = ParagraphStyle('To', parent=body_style, alignment=TA_JUSTIFY, leftIndent=0)
            story.append(Paragraph(line.replace("\n","<br/>"), body_style))
        elif line.startswith("Subject:"):
            story.append(Paragraph(f"<b>{line}</b>", subject_style))
        elif line.startswith("Respected") or line.startswith("With regards") or line.startswith("Thank you"):
            story.append(Paragraph(line, body_style))
        elif "Chairperson" in line or "Staff In Charge" in line or "Arthana" in line or "Aysha" in line:
            story.append(Paragraph(line, sign_style))
        else:
            story.append(Paragraph(line, body_style))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def permission_letter_pdf(letter_text: str) -> bytes:
    return _build_pdf(letter_text, title="")

def onfoot_letter_pdf(letter_text: str) -> bytes:
    return _build_pdf(letter_text, title="")

def announcement_pdf(announcement_text: str) -> bytes:
    return _build_pdf(announcement_text, title="Event Announcement")
