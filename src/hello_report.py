from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def build_pdf(out_path="reports/Hello_CA_Report.pdf"):
    doc = SimpleDocTemplate(out_path, pagesize=letter,
                            leftMargin=0.5*inch, rightMargin=0.5*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Alameda Unified Educational Report", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "This is a smoke test to confirm our PDF toolchain works. "
        "Next step: wire in real data, charts, and deterministic tables.",
        styles["BodyText"]))
    doc.build(story)

if __name__ == "__main__":
    build_pdf()
