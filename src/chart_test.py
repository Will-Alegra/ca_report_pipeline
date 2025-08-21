import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Image, Spacer
from reportlab.lib.units import inch

# Step 1: Make a simple chart
grades = ["K", "1", "2", "3", "4", "5"]
enrollment = [400, 420, 700, 680, 950, 720]

plt.bar(grades, enrollment, color="#4FA3F7")
plt.title("Enrollment by Grade")
plt.ylabel("Students")
plt.savefig("reports/enrollment_chart.png", bbox_inches="tight")
plt.close()

# Step 2: Put chart in a PDF
doc = SimpleDocTemplate("reports/Chart_Test_Report.pdf", pagesize=letter)
story = []
story.append(Image("reports/enrollment_chart.png", width=5*inch, height=3*inch))
story.append(Spacer(1, 12))
doc.build(story)
