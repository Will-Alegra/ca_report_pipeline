import os
from datetime import date
import math
import pandas as pd
import sys

# ---- Charts (matplotlib) ----
import matplotlib.pyplot as plt

# ---- PDF (reportlab) ----
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, LongTable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import ListFlowable, ListItem



#----- real data import form our save files-----
from fetch_enrollment_ca import fetch_enrollment_from_txt

from caaspp_summary import summarize_district_ela
from caaspp_summary import district_ela_by_grade
from fetch_elpac import district_elpac_speaking_by_grade
from caaspp_summary import district_ela_pct_below_standard_by_grade
from fetch_elpac import district_elpac_speaking_pct_below_by_grade
from fetch_enrollment_ca import fetch_enrollment_from_txt, fetch_enrollment_school_row






#debug script to tell all the names of districts in the files
# --- DEBUG: list district names once, then remove ---
# from fetch_elpac import load_elpac
# from fetch_caaspp import load_caaspp

# try:
#     df_elpac = load_elpac()
#     df_caaspp = load_caaspp()
#     print("ELPAC districts (sample):",
#           sorted(df_elpac["District Name"].dropna().unique())[:50])
#     print("CAASPP districts (sample):",
#           sorted(df_caaspp["District Name"].dropna().unique())[:50])
# except Exception as e:
#     print("[debug list] error:", e)
# ----------------------------------------------------





# -----------------------------
# Config
# -----------------------------





#---------main config

IMG_DIR = "reports/_tmp"
PAGE_MARGINS = dict(left=0.5*inch, right=0.5*inch, top=0.5*inch, bottom=0.5*inch)
CHART_W_IN = 6.5  # fixed chart slot width
CHART_H_IN = 3.2  # fixed chart slot height
CHART_W_PX = 1300
CHART_H_PX = 640
ROW_HEIGHT = 18  # points; tweak for readability
GRADES_K5 = ["K", "1", "2", "3", "4", "5"]


#future improvement: there is a way to call what district you want to access when you run the code, such as "python build_report.py -Alameda unified"
# -----------------------------
# District names
# -----------------------------
#district_name = "Alameda Unified"
#district_name = "Irvine Unified"

#--------editable variables
#note: this is not fully set up, and I dont remember if this works on all or only some of the 3 graphs
#future improvment: fix charters toggle
INCLUDE_CHARTERS = False   # set True if you want them included

# ---------- Entity selection ----------
# Choose whether this report is for a whole DISTRICT or a single SCHOOL.
# by default the code will run with a command line such as: python src/build_report.py district "Irvine Unified"
#if the district/school and its name is not stated in the run command, THEN it will default to the following after looking at in the run line first. 
ENTITY_TYPE = "district"   # or "school"
#ENTITY_TYPE = "school"
ENTITY_NAME = "Irvine Unified"   # e.g., "Alameda Unified" or "ARISE High"
#ENTITY_NAME = "ARISE High"
# -------------------------------------

ela_info = summarize_district_ela(ENTITY_TYPE, ENTITY_NAME)

# --- DEBUG: print a sample of districts from both files (remove after use) --- (currently this is set up to only show the first 50 results of both)
# from fetch_elpac import list_districts as elpac_districts
# from fetch_caaspp import list_districts as caaspp_districts

# print("ELPAC districts (sample):", elpac_districts())
# print("CAASPP districts (sample):", caaspp_districts())
# ---------------------------------------------------------------------------

grades = ["K", "1", "2", "3", "4", "5"]


# -----------------------------
# Helpers
# -----------------------------
def ensure_dirs():
    os.makedirs("reports", exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)

# in build_report.py
def save_bar_chart_with_na(labels, values, out_png, title="", y_label="", cut_scores=None, y_max=None):
    import matplotlib.pyplot as plt
    import math
    xs = range(len(labels))
    heights = [0 if (v is None or (isinstance(v, float) and math.isnan(v))) else v for v in values]

    plt.figure(figsize=(CHART_W_IN, CHART_H_IN))
    plt.bar(xs, heights)
    plt.xticks(xs, labels)
    plt.title(title)
    plt.ylabel(y_label)
    if y_max is not None:
        plt.ylim(0, y_max)

    for i, v in enumerate(values):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            plt.text(i, 0.5, "N/A", ha="center", va="bottom", fontsize=9)

    # (cut_scores ignored for this chart type)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()

def get_enrollment_for_report(entity_type: str, entity_name: str):
    """
    Returns a DataFrame shaped like:
      School | K | 1 | 2 | 3 | 4 | 5 | Total
    For DISTRICT: existing behavior (all schools in the district).
    For SCHOOL: filters the district table down to that one school.
    """
    # reuse your existing district fetcher
    # df_all = fetch_enrollment_from_txt(entity_name if entity_type == "district" else None)

    # if entity_type == "district":
    #     return df_all
    
    if entity_type == "district":
        return fetch_enrollment_from_txt(entity_name)

    # SCHOOL mode:
    if entity_type == "school":
        return fetch_enrollment_school_row(entity_name)

    raise ValueError(f"Unknown entity_type: {entity_type}")

    # SCHOOL mode: we don't have a direct school-only fetch yet.
    # Strategy: find which district contains this school, then filter.
    # Easiest: search districts that contain the school by name.
    # We’ll do a simple scan by trying a few likely districts (fast-enough for now):
    # Fallback: try Alameda Unified as a default search scope (adjust as needed).
    # ----
    # Better approach: prompt the user for the district of the school. For now, try to guess.

    # Try to find the district by scanning a few common districts (quick heuristic)
    # If you know the district, replace this list with [that_district].
    candidate_districts = [
        "Alameda Unified", "Irvine Unified", "Los Angeles Unified", "San Diego Unified"
    ]

    for d in [*candidate_districts, entity_name]:
        try:
            df_d = fetch_enrollment_from_txt(d)
            # exact/contains match on School column
            mask = df_d["School"].astype(str).str.strip().str.lower() == entity_name.strip().lower()
            if mask.any():
                return df_d.loc[mask].reset_index(drop=True)
        except Exception:
            pass

    # If we got here, we didn’t find that school in our quick scan.
    # Return an empty DF with the right columns so the caller can handle gracefully.
    cols = ["School","K","1","2","3","4","5","Total"]
    return pd.DataFrame(columns=cols)



def save_bar_chart_enrollment(grades, counts, out_png):
    plt.figure(figsize=(CHART_W_PX/100, CHART_H_PX/100), dpi=100)
    plt.bar(grades, counts)
    plt.title("Enrollment by Grade")
    plt.ylabel("Students")
    plt.tight_layout()
    plt.savefig(out_png, bbox_inches="tight")
    plt.close()

def save_bar_chart_reading_gap(labels, pct_below, out_png):
    """
    Reused name: accepts labels ['1'..'5'] and pct_below (None for 1–2).
    Draws % below standard with tight Y axis + bar labels.
    """
    import matplotlib.pyplot as plt
    from math import ceil

    values = [v if v is not None else 0 for v in pct_below]
    valid = [v for v in pct_below if isinstance(v, (int, float))]
    maxv = max(valid) if valid else 0
    y_max = min(100, ceil(maxv / 5.0) * 5 + 5)
    if y_max < 30:
        y_max = 30

    # keep your existing sizing constants if you have them
    fig = plt.figure(figsize=(CHART_W_PX/100, CHART_H_PX/100), dpi=100)
    ax = fig.add_subplot(111)

    bars = ax.bar(labels, values)
    ax.set_ylim(0, y_max)
    ax.set_ylabel("% Below Standard (L1 + L2)")
    ax.set_title("Reading Gap by Grade")
    #"CAASPP ELA — % of Students Below Standard (Levels 1+2) by Grade"

    pad = y_max * 0.02
    for bar, v in zip(bars, pct_below):
        x = bar.get_x() + bar.get_width() / 2
        if v is None:
            ax.text(x, pad, "N/A", ha="center", va="bottom", fontsize=10)
        else:
            ax.text(x, bar.get_height() + pad, f"{v:.0f}%", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

def save_bar_chart_elpac_speaking(labels, levels, out_png):
    """
    labels: ['1','2','3','4','5']
    levels: average speaking performance level per grade (1–3), or None for missing
    """
    import math
    import matplotlib.pyplot as plt

    # Plot 0 when missing; we’ll overlay “N/A”
    values = [v if v is not None else 0.0 for v in levels]

    # Dynamic y-axis: headroom above max (cap near 3.2 since levels run 1–3)
    valid = [v for v in levels if isinstance(v, (int, float))]
    maxv  = max(valid) if valid else 0.0
    y_max = min(3.2, round(max(2.0, maxv + 0.15), 2))  # gentle headroom
    y_min = 0.8  # keeps labels readable; below level 1

    fig = plt.figure(figsize=(CHART_W_PX/100, CHART_H_PX/100), dpi=100)
    ax = fig.add_subplot(111)

    bars = ax.bar(labels, values)

    ax.set_ylim(y_min, y_max)
    ax.set_ylabel("Avg Speaking Performance Level (1–3)")
    ax.set_title("ELPAC Speaking — Average Performance Level by Grade")

    # Labels on bars
    pad = (y_max - y_min) * 0.03
    for bar, raw in zip(bars, levels):
        x = bar.get_x() + bar.get_width() / 2
        if raw is None:
            ax.text(x, y_min + pad, "N/A", ha="center", va="bottom", fontsize=10)
        else:
            ax.text(x, bar.get_height() + pad, f"{raw:.1f}", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

def save_bar_chart_elpac_pct_below(labels, pct_below, out_png):
    """
    labels: ['1','2','3','4','5']
    pct_below: list of percents (0–100) or None
    """
    import matplotlib.pyplot as plt
    from math import ceil

    values = [v if v is not None else 0 for v in pct_below]
    valid  = [v for v in pct_below if isinstance(v, (int, float))]
    maxv   = max(valid) if valid else 0
    y_max  = min(100, ceil(maxv / 5.0) * 5 + 5)
    if y_max < 30:
        y_max = 30

    fig = plt.figure(figsize=(CHART_W_PX/100, CHART_H_PX/100), dpi=100)
    ax = fig.add_subplot(111)
    bars = ax.bar(labels, values)

    ax.set_ylim(0, y_max)
    ax.set_ylabel("% in Levels 1 + 2 (Speaking)")
    ax.set_title("Speaking Gap by Grade")
    #"ELPAC Speaking — % Below 'Developed' (Levels 1+2) by Grade")

    pad = y_max * 0.02
    for bar, v in zip(bars, pct_below):
        x = bar.get_x() + bar.get_width() / 2
        if v is None:
            ax.text(x, pad, "N/A", ha="center", va="bottom", fontsize=10)
        else:
            ax.text(x, bar.get_height() + pad, f"{v:.0f}%", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def kpi_tiles(total_k5: int, avg_read_gap: float, avg_speak_gap: float):
    """
    Returns a Platypus Table that shows 3 KPI tiles.
    """
    styles = getSampleStyleSheet()
    tile_style = ParagraphStyle(
        "Tile", parent=styles["Heading3"], alignment=1, textColor=colors.white
    )
    val_style = ParagraphStyle(
        "Val", parent=styles["Title"], alignment=1, textColor=colors.white
    )
    # Format values
    k1 = Paragraph("Total K-5 Enrollment", tile_style)
    v1 = Paragraph(f"{total_k5:,}", val_style)

    k2 = Paragraph("Avg Reading Gap (3–5)", tile_style)
    v2 = Paragraph(f"{avg_read_gap*100:.0f}%", val_style)

    k3 = Paragraph("Avg Speaking Gap (K–5 ELs)", tile_style)
    v3 = Paragraph(f"{avg_speak_gap*100:.0f}%", val_style)

    data = [
        [v1, v2, v3],
        [k1, k2, k3],
    ]
    t = Table(data, colWidths=[2.8*inch, 2.8*inch, 2.8*inch], rowHeights=[0.9*inch, 0.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563EB")),  # values row
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#1E40AF")),  # labels row
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ("INNERGRID", (0,0), (-1,-1), 0.0, colors.white),
        ("BOX", (0,0), (-1,-1), 0.0, colors.white),
        ("BOTTOMPADDING", (0,1), (-1,1), 6),
    ]))
    return t

def footnote_paragraph():
    styles = getSampleStyleSheet()
    note = (
        "Notes: Reading reflects CAASPP (typically grades 3–5 at elementary). "
        "K–2 are not assessed on CAASPP. Speaking gap is based on ELPAC thresholds for English Learners."
    )
    return Paragraph(note, styles["BodyText"])

from caaspp_summary import district_ela_by_grade

# Page: Enrollment (Grades 1–5)
def build_page_enrollment(story, df_enr):
    styles = getSampleStyleSheet()
    story.append(PageBreak())
    story.append(Paragraph("Enrollment by Grade (1–5)", styles["Heading2"]))
    story.append(Spacer(1, 8))

    labels = ["1","2","3","4","5"]
    by_grade = [int(df_enr[g].sum()) if g in df_enr.columns else 0 for g in labels]

    png = os.path.join(IMG_DIR, "enrollment_g1_5.png")
    save_bar_chart_with_na(labels, by_grade, png, title="Enrollment by Grade (1–5)", y_label="Students")
    story.append(Image(png, width=CHART_W_IN*inch, height=CHART_H_IN*inch))



def build_page_caaspp_ela(story, entity_type, entity_name):
    styles = getSampleStyleSheet()
    story.append(PageBreak())
    story.append(Paragraph("Reading (CAASPP ELA) — % Not Meeting Standard", styles["Heading2"]))
    story.append(Spacer(1, 8))

    if entity_type == "school":
        story.append(Paragraph("School-level CAASPP wiring coming soon.", styles["Italic"]))
        return

    labels, pct_below, _tested = district_ela_pct_below_standard_by_grade(entity_name)

    png = os.path.join(IMG_DIR, "caaspp_ela_pct_below_g1_5.png")
    save_bar_chart_reading_gap(labels, pct_below, png)

    story.append(Image(png, width=CHART_W_IN*inch, height=CHART_H_IN*inch))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        """Note: CAASPP ELA is administered starting in grade 3; grades 1–2 display as N/A.<br/>
        <br/>
        Level 1 = Standard Not Met<br/>
        Level 2 = Standard Nearly Met<br/>
        Level 3 = Standard Met<br/>
        Level 4 = Standard Exceeded<br/>
        (Chart displays % of students in Levels 1 + 2)""",
        styles["Italic"]
    ))




def build_page_elpac_speaking(story, entity_type, entity_name):
    styles = getSampleStyleSheet()
    story.append(PageBreak())
    story.append(Paragraph("Speaking (ELPAC) by Grade (1–5)", styles["Heading2"]))
    story.append(Spacer(1, 8))

    if entity_type == "school":
        story.append(Paragraph("School-level ELPAC wiring coming soon.", styles["Italic"]))
        return

    # % below Developed (Levels 1+2)
    labels, pct_below, _tested = district_elpac_speaking_pct_below_by_grade(entity_name)

    png = os.path.join(IMG_DIR, "elpac_speaking_pct_below_g1_5.png")
    save_bar_chart_elpac_pct_below(labels, pct_below, png)

    story.append(Image(png, width=CHART_W_IN*inch, height=CHART_H_IN*inch))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        """Note: ELPAC Speaking uses performance levels.
        <br/><br/>
        <b>Level 1</b> = Begin<br/>
        <b>Level 2</b> = Moderate<br/>
        <b>Level 3</b> = Developed<br/>
        (Chart shows the percentage of students in Levels 1 + 2 per grade.)""",
        styles["Italic"]
    ))


def build_school_table_flowables(headers, rows):
    """
    Returns a list of flowables that render a table which:
      - repeats headers on every page
      - uses a fixed row height
      - auto page-breaks cleanly
    """
    # Combine header + rows
    table_data = [headers] + rows

    # LongTable will handle page breaks; we style for consistency
    t = LongTable(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E5E7EB")),  # header gray
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#9CA3AF")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), (ROW_HEIGHT-12)/2),   # center text vertically
        ("BOTTOMPADDING", (0,0), (-1,-1), (ROW_HEIGHT-12)/2),
    ]))
    return [t]


def save_top10_schools_chart(rows, out_png):
    """
    rows: list of lists, where row[0] is school name, row[1:-1] are grades, row[-1] is total enrollment.
    """
    # Sort by total enrollment (last column), descending
    sorted_rows = sorted(rows, key=lambda r: r[-1], reverse=True)
    top10 = sorted_rows[:10]
    schools = [r[0] for r in top10]
    totals = [r[-1] for r in top10]

    plt.figure(figsize=(CHART_W_PX/100, CHART_H_PX/100), dpi=100)
    plt.barh(schools, totals)
    plt.gca().invert_yaxis()  # highest at top
    plt.title("Top 10 Schools by K–5 Enrollment")
    plt.xlabel("Students")
    plt.tight_layout()
    plt.savefig(out_png, bbox_inches="tight")
    plt.close()


# -----------------------------
# Build Pages functions
# -----------------------------
# def build_page_one(doc, story, df_enr, ela_info):
#     styles = getSampleStyleSheet()
#     title = Paragraph(f"{district_name} — Executive Summary", styles["Title"])




def build_page_one(doc, story, df_enr, ela_info=None, entity_type="district", entity_name=""):
    styles = getSampleStyleSheet()
    heading = f"{entity_name} — Executive Summary" if entity_name else "Executive Summary"
    title = Paragraph(heading, styles["Title"])
    date_p = Paragraph(date.today().strftime("%B %d, %Y"), styles["Normal"])
    story += [title, date_p, Spacer(1, 12)]

    # --- KPIs from real data ---
    total_k5 = int(df_enr["Total"].sum())

    # Real CAASPP ELA metrics (district-level)
    ela_avg = ela_info.get("avg_scale_score")
    ela_gap_vs_benchmark = ela_info.get("gap_vs_benchmark")  # positive = above 2500
    ela_tested = ela_info.get("tested")  # available if you want to show later

    kpi_tiles_list = [
        ("Total K-5 Enrollment", f"{total_k5:,}"),
        #commenting out the 2 peices of info with direct CAASPP score and Total average compared to benchmark
        #("Reading (CAASPP) Avg", f"{ela_avg:.1f}" if ela_avg is not None else "–"),
        #("Gap vs Standard (2500)", f"{ela_gap_vs_benchmark:+.1f}" if ela_gap_vs_benchmark is not None else "–"),
    ]
    for label, value in kpi_tiles_list:
        story.append(Paragraph(f"<b>{label}:</b> {value}", styles["BodyText"]))
    story.append(Spacer(1, 14))

    # --- Enrollment by Grade (1–5) on Page 1 ---
    labels = ["1", "2", "3", "4", "5"]
    by_grade = [int(df_enr[g].sum()) if g in df_enr.columns else 0 for g in labels]

    enroll_png = os.path.join(IMG_DIR, "enrollment_g1_5.png")
    save_bar_chart_with_na(labels, by_grade, enroll_png,
                           title="Enrollment by Grade (1–5)",
                           y_label="Students")

    enroll_img = Image(enroll_png, width=CHART_W_IN*inch, height=CHART_H_IN*inch)
    story.append(enroll_img)
    story.append(Spacer(1, 10))



# def build_page_two_enrollment_table(story, df_enr, entity_type="district", entity_name=""):
#     styles = getSampleStyleSheet()
#     story.append(PageBreak())
#     story.append(Paragraph(
#         "Enrollment by School (K–5)" if entity_type == "district" else f"Enrollment — {entity_name} (K–5)",
#         styles["Heading2"]
#     ))
#     story.append(Spacer(1, 6))

#     # If SCHOOL mode, df_enr will be a single row (one school) — that’s fine.
#     headers = ["School", "K", "1", "2", "3", "4", "5", "Total"]
#     rows = df_enr[headers].values.tolist()
#     # Top-10 chart only really applies in district mode; skip in school mode.
#     if entity_type == "district":
#         top10_png = os.path.join(IMG_DIR, "top10_schools.png")
#         save_top10_schools_chart(rows, top10_png)
#         story.append(Image(top10_png, width=CHART_W_IN*inch, height=CHART_H_IN*inch))
#         story.append(Spacer(1, 12))

#     story += build_school_table_flowables(headers, rows)

def sanitize_filename(name: str) -> str:
    """Turn 'Irvine Unified' into 'Irvine_Unified'."""
    return name.replace(" ", "_").replace("/", "-")

def build_references_page(story):
    styles = getSampleStyleSheet()
    story.append(PageBreak())
    story.append(Paragraph("Data Sources & References", styles["Heading2"]))
    story.append(Spacer(1, 6))

    accessed = date.today().strftime("%B %d, %Y")

    refs = [
        {
            "title": "California Department of Education — Enrollment by Grade (2024–25)",
            "desc": "Official enrollment counts by grade for all public schools and districts in California.",
            "url": "https://www.cde.ca.gov/ds/sd/sd/",
        },
        {
            "title": "CAASPP Research Files — 2024 ELA Summative Assessment",
            "desc": "ELA (English Language Arts) results for grades 3–8 and 11, including mean scale scores and proficiency levels.",
            "url": "https://caaspp-elpac.ets.org/caaspp/ResearchFileListSB.aspx",
        },
        {
            "title": "CAASPP Program Overview & Documentation",
            "desc": "Benchmarks and performance level descriptors for CAASPP ELA.",
            "url": "https://www.cde.ca.gov/ta/tg/ca/",
        },
        {
            "title": "ELPAC Research Files — 2024 Summative Assessment",
            "desc": "Speaking domain results for grades 1–5, including performance levels and counts for California public schools and districts.",
            "url": "https://www.cde.ca.gov/ta/tg/ep/elpacresearch.asp",
        },
        {
            "title": "ELPAC Program Overview & Documentation",
            "desc": "Benchmarks, domains, and performance level descriptors for the ELPAC.",
            "url": "https://www.cde.ca.gov/ta/tg/ep/",
        },
    ]

    items = []
    for r in refs:
        html = (
            f"<b>{r['title']}</b><br/>"
            f"<font size=9>{r['desc']}</font><br/>"
            f"<font size=9>Accessed: {accessed}</font><br/>"
            f'<a href="{r["url"]}">{r["url"]}</a>'
        )
        items.append(ListItem(Paragraph(html, styles["BodyText"]), leftIndent=6, value="•"))

    story.append(ListFlowable(items, bulletType="bullet", start="•"))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Notes: Enrollment is sourced from CDE’s statewide census file; CAASPP ELA results are computed as weighted averages across tested grades. "
        "District-level CAASPP rows are identified by School Code 0000000; “All Students” corresponds to Student Group ID 1.",
        styles["Italic"]
    ))


def build_pdf(entity_type, entity_name, out_path=None):
    # 0) Resolve output path
    if out_path is None:
        safe_name = entity_name.replace(" ", "_")
        out_path = f"reports/{safe_name}_Report.pdf"

    ensure_dirs()

    # 1) Prepare doc + story
    doc = SimpleDocTemplate(out_path, pagesize=letter, **PAGE_MARGINS)
    story = []

    # 2) Data
    df_enr = get_enrollment_for_report(entity_type, entity_name)

    try:
        ela_info = summarize_district_ela(entity_type, entity_name)
    except Exception as e:
        print("[warn] ELA summary failed:", e)
        ela_info = {}

    # 3) Build pages
    build_page_one(
        doc,
        story,
        df_enr,
        ela_info=ela_info,
        entity_type=entity_type,
        entity_name=entity_name,
    )
    build_page_caaspp_ela(story, entity_type, entity_name)   # % below standard
    build_page_elpac_speaking(story, entity_type, entity_name)
    build_references_page(story)

    # 4) Write file
    doc.build(story)

    # 5) Return path (no printing here; do it in __main__)
    return out_path



if __name__ == "__main__":
    import sys

    # Optional globals near the top of the file:
    # ENTITY_TYPE = "district"   # or "school"
    # ENTITY_NAME = "Irvine Unified"

    # CLI overrides globals if provided:
    #   python src/build_report.py
    #   python src/build_report.py district "Alameda Unified"
    #   python src/build_report.py school "ARISE High"
    if len(sys.argv) >= 3:
        etype = sys.argv[1].strip().lower()       # "district" | "school"
        ename = " ".join(sys.argv[2:]).strip()
    else:
        # Fall back to globals if you’ve set them; otherwise use defaults
        etype = (globals().get("ENTITY_TYPE") or "district").strip().lower()
        ename = (globals().get("ENTITY_NAME") or "Alameda Unified").strip()

    print(f"[info] Building report for {etype!r}: {ename}")
    out_path = build_pdf(etype, ename)
    print(f"[info] PDF successfully built at: {out_path}")

