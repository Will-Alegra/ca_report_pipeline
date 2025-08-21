# src/caaspp_summary.py
import re
import pandas as pd
from pathlib import Path

# Resolve paths relative to the repo root (one level up from src/)
BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CAASPP_PATH = BASE_DIR / "data_raw" / "caaspp_2024_ela.txt"

BENCHMARK = 2500.0
VALID_GRADES = {"3", "4", "5", "6", "7", "8", "11"}
ALL_STUDENTS_ID = "1"  # All Students subgroup id in the CAASPP file

def _read_caaspp(filepath: str | None = None) -> pd.DataFrame:
    """
    Read the statewide CAASPP ELA research file (caret-delimited).
    If `filepath` is None or relative, resolve it relative to the repo root.
    """
    path = Path(filepath) if filepath else DEFAULT_CAASPP_PATH
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Put the CAASPP ELA research file there.")

    # CAASPP research files are caret-delimited with headers on the first row
    return pd.read_csv(path, sep="^", engine="python", header=0, dtype=str, encoding="latin1")


# --- % Below Standard (Not Met + Nearly Met) by grade for a district ---
def district_ela_pct_below_standard_by_grade(district_name: str, filepath: str | None = None):
    """
    Returns (labels, pct_below, tested) for grades 1–5, where:
      pct_below = Percentage Standard Not Met + Percentage Standard Nearly Met (0–100)
    Source rows: district-level (School Code 0/0000000), All Students (Student Group ID = 1).
    """
    df = _read_caaspp(filepath)  # <-- single source of truth for path + reading

    # Column names in the statewide research file
    COL_DNAME  = "District Name"
    COL_SCODE  = "School Code"
    COL_SGID   = "Student Group ID"
    COL_GRADE  = "Grade"
    # prefer Tested-with-scores if present, else Total Tested
    COL_TESTED = (
        "Total Students Tested with Scores"
        if "Total Students Tested with Scores" in df.columns
        else "Total Students Tested"
    )
    COL_PCT_L1 = "Percentage Standard Not Met"
    COL_PCT_L2 = "Percentage Standard Nearly Met"

    required = [COL_DNAME, COL_SCODE, COL_SGID, COL_GRADE, COL_TESTED, COL_PCT_L1, COL_PCT_L2]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CAASPP: missing columns {missing}\nHave: {list(df.columns)}")

    # District match (tolerant of 'School District' suffix)
    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
    target = norm(district_name).lower()
    work = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)].copy()
    if work.empty:
        raise ValueError(f"No CAASPP rows found for district containing '{district_name}'.")

    # District-level only (School Code == 0 or 0000000)
    sc = work[COL_SCODE].astype(str).str.strip()
    work = work[(sc == "0") | (sc == "0000000")].copy()
    if work.empty:
        raise ValueError("Found district, but no district-level rows (School Code == 0000000).")

    # All Students, CAASPP-valid grades
    work = work[work[COL_SGID].astype(str).str.strip() == ALL_STUDENTS_ID].copy()
    work[COL_GRADE] = work[COL_GRADE].astype(str).str.strip()
    valid_caaspp = {"3", "4", "5", "6", "7", "8", "11"}
    work = work[work[COL_GRADE].isin(valid_caaspp)].copy()

    # Coerce numerics
    work[COL_TESTED] = pd.to_numeric(work[COL_TESTED], errors="coerce").fillna(0).astype(int)
    work[COL_PCT_L1] = pd.to_numeric(work[COL_PCT_L1], errors="coerce")  # already percentages 0–100
    work[COL_PCT_L2] = pd.to_numeric(work[COL_PCT_L2], errors="coerce")

    # One row per grade: pick the largest tested count when duplicates exist
    work = (
        work.sort_values([COL_GRADE, COL_TESTED], ascending=[True, False])
            .drop_duplicates(subset=[COL_GRADE], keep="first")
    )

    # Output x-axis 1–5 (grades 1–2 will show None/N/A)
    axis = ["1", "2", "3", "4", "5"]
    pct_map  = {g: None for g in axis}
    test_map = {g: 0    for g in axis}

    for _, r in work.iterrows():
        g = r[COL_GRADE]                      # '3','4','5',...
        if g in pct_map:                      # only fills 3–5; 1–2 stay None
            p = (r[COL_PCT_L1] if pd.notna(r[COL_PCT_L1]) else 0.0) + \
                (r[COL_PCT_L2] if pd.notna(r[COL_PCT_L2]) else 0.0)
            pct_map[g]  = float(p)
            test_map[g] = int(r[COL_TESTED])

    labels    = axis
    pct_below = [pct_map[g]  for g in labels]  # [None, None, %, %, %]
    tested    = [test_map[g] for g in labels]  # [0, 0, n, n, n]
    return labels, pct_below, tested

def district_ela_by_grade(district_name: str, filepath: str | None = None):
    """
    Returns (axis, scores, tested):

      axis   -> ['1','2','3','4','5']
      scores -> mean scale score per grade (None for 1–2 since CAASPP starts at 3)
      tested -> students tested per grade (0 for 1–2)

    Filters to district-level rows (School Code 0/0000000),
    All Students (Student Group ID=1), and for each grade keeps the row
    with the largest tested count.
    """
    df = _read_caaspp(filepath)

    COL_DNAME  = "District Name"
    COL_SCODE  = "School Code"
    COL_SGID   = "Student Group ID"
    COL_GRADE  = "Grade"
    COL_TESTED = (
        "Total Students Tested with Scores"
        if "Total Students Tested with Scores" in df.columns
        else "Total Students Tested"
    )
    COL_AVG    = "Mean Scale Score"

    # District match (tolerant of “School District” suffix)
    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
    target = norm(district_name).lower()
    work = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)].copy()

    # District-level only
    sc = work[COL_SCODE].astype(str).str.strip()
    work = work[(sc == "0") | (sc == "0000000")].copy()

    # All Students, CAASPP-valid grades
    work = work[work[COL_SGID].astype(str).str.strip() == ALL_STUDENTS_ID].copy()
    work[COL_GRADE] = work[COL_GRADE].astype(str).str.strip()
    work = work[work[COL_GRADE].isin(VALID_GRADES)].copy()  # {'3','4','5','6','7','8','11'}

    # Numerics
    work[COL_TESTED] = pd.to_numeric(work[COL_TESTED], errors="coerce").fillna(0).astype(int)
    work[COL_AVG]    = pd.to_numeric(work[COL_AVG],    errors="coerce")

    # One row per grade (largest tested)
    work = (
        work.sort_values([COL_GRADE, COL_TESTED], ascending=[True, False])
            .drop_duplicates(subset=[COL_GRADE], keep="first")
    )

    # Map to 1–5 axis
    axis = ["1", "2", "3", "4", "5"]
    score_map  = {g: None for g in axis}
    tested_map = {g: 0    for g in axis}

    for _, r in work.iterrows():
        g = r[COL_GRADE]  # '3','4','5',...
        if g in score_map:
            score_map[g]  = float(r[COL_AVG]) if pd.notna(r[COL_AVG]) else None
            tested_map[g] = int(r[COL_TESTED])

    scores = [score_map[g]  for g in axis]
    tested = [tested_map[g] for g in axis]
    return axis, scores, tested

# put near the top with your other imports/utilities
def _pick_col(df, candidates):
    """Return the first candidate column that exists in df, else raise."""
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"None of the columns found: {candidates}. Have: {list(df.columns)}")


def summarize_district_ela(entity_type: str,
                  entity_name: str,
                  filepath: str | None = None,
                  benchmark: float = BENCHMARK) -> dict:
    """
    Compute weighted-average CAASPP ELA scale score and gap vs benchmark
    for either a DISTRICT or a SCHOOL.
    """
    df = _read_caaspp(filepath)

    # column names (handle both spaced and unspaced variants)
    COL_DNAME  = _pick_col(df, ["District Name", "DistrictName"])
    COL_SNAME  = _pick_col(df, ["School Name", "SchoolName"])
    COL_SCODE  = _pick_col(df, ["School Code", "SchoolCode"])
    COL_SGID   = _pick_col(df, ["Student Group ID", "StudentGroupID"])
    COL_GRADE  = _pick_col(df, ["Grade"])
    COL_AVG    = _pick_col(df, ["Mean Scale Score", "MeanScaleScore"])
    COL_TESTED = "Total Students Tested with Scores" if "Total Students Tested with Scores" in df.columns \
                 else _pick_col(df, ["Total Students Tested", "TotalTested"])

    # filter by entity
    if entity_type.lower() == "district":
        # district-level rows only (School Code 0/0000000)
        sc = df[COL_SCODE].astype(str).str.strip()
        work = df[(df[COL_DNAME].astype(str).str.strip() == entity_name) &
                  ((sc == "0") | (sc == "0000000"))].copy()
    elif entity_type.lower() == "school":
        # school-level rows (School Code != 0)
        sc = df[COL_SCODE].astype(str).str.strip()
        work = df[(df[COL_SNAME].astype(str).str.strip() == entity_name) &
                  ((sc != "0") & (sc != "0000000"))].copy()
    else:
        raise ValueError(f"Unknown entity_type: {entity_type}")

    if work.empty:
        raise ValueError(f"No CAASPP rows found for {entity_type}='{entity_name}'.")

    # All Students, tested grades only (3–8,11)
    work = work[work[COL_SGID].astype(str).str.strip() == "1"].copy()
    work[COL_GRADE] = work[COL_GRADE].astype(str).str.strip()
    work = work[work[COL_GRADE].isin({"3", "4", "5", "6", "7", "8", "11"})].copy()

    # numerics
    work[COL_TESTED] = pd.to_numeric(work[COL_TESTED], errors="coerce").fillna(0).astype(int)
    work[COL_AVG]    = pd.to_numeric(work[COL_AVG], errors="coerce")

    # one row per grade (largest tested count)
    work = (work.sort_values([COL_GRADE, COL_TESTED], ascending=[True, False])
                .drop_duplicates(subset=[COL_GRADE], keep="first"))

    tested = int(work[COL_TESTED].sum())
    weighted_sum = float((work[COL_AVG] * work[COL_TESTED]).sum())
    avg_scale = (weighted_sum / tested) if tested > 0 else float("nan")
    gap_vs_benchmark = (avg_scale - benchmark) if pd.notna(avg_scale) else float("nan")

    label = entity_name
    return {
        "entity": label,
        "entity_type": entity_type,
        "avg_scale_score": round(avg_scale, 1) if pd.notna(avg_scale) else None,
        "gap_vs_benchmark": round(gap_vs_benchmark, 1) if pd.notna(gap_vs_benchmark) else None,
        "tested": tested,
    }


# def summarize_district_ela(district_name: str, filepath: str | None = None, benchmark: float = BENCHMARK) -> dict:
#     """
#     Weighted-average mean scale score for grades 3–8 & 11 at the district level,
#     All Students (Student Group ID=1), plus gap vs benchmark.
#     """
#     #df = _read_caaspp(filepath)
#     df = _read_caaspp()  # just load the dataset from disk

#     if entity_type == "district":
#         df = df[df["DistrictName"] == entity_name]
#     elif entity_type == "school":
#         df = df[df["SchoolName"] == entity_name]


#     COL_DNAME  = "District Name"
#     COL_SCODE  = "School Code"
#     COL_SGID   = "Student Group ID"
#     COL_GRADE  = "Grade"
#     COL_TESTED = (
#         "Total Students Tested with Scores"
#         if "Total Students Tested with Scores" in df.columns
#         else "Total Students Tested"
#     )
#     COL_AVG    = "Mean Scale Score"

#     required = [COL_DNAME, COL_SCODE, COL_SGID, COL_GRADE, COL_TESTED, COL_AVG]
#     missing = [c for c in required if c not in df.columns]
#     if missing:
#         raise ValueError(f"Required columns missing: {missing}\nHave: {list(df.columns)}")

#     # Filter to district (tolerant)
#     norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
#     target = norm(district_name).lower()
#     work = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)].copy()
#     if work.empty:
#         raise ValueError(f"No CAASPP rows found for district containing '{district_name}'.")

#     # District-level, All Students, valid grades
#     sc = work[COL_SCODE].astype(str).str.strip()
#     work = work[(sc == "0") | (sc == "0000000")].copy()
#     if work.empty:
#         raise ValueError("Found district, but no district-level rows (School Code == 0000000).")

#     work = work[work[COL_SGID].astype(str).str.strip() == ALL_STUDENTS_ID].copy()
#     work[COL_GRADE] = work[COL_GRADE].astype(str).str.strip()
#     work = work[work[COL_GRADE].isin(VALID_GRADES)].copy()

#     # Numerics
#     work[COL_TESTED] = pd.to_numeric(work[COL_TESTED], errors="coerce").fillna(0).astype(int)
#     work[COL_AVG]    = pd.to_numeric(work[COL_AVG],    errors="coerce")

#     # One row per grade (largest tested), then weighted average
#     work = (
#         work.sort_values([COL_GRADE, COL_TESTED], ascending=[True, False])
#             .drop_duplicates(subset=[COL_GRADE], keep="first")
#     )

#     tested = int(work[COL_TESTED].sum())
#     weighted_sum = float((work[COL_AVG] * work[COL_TESTED]).sum())
#     avg_scale = (weighted_sum / tested) if tested > 0 else float("nan")
#     gap_vs_benchmark = (avg_scale - benchmark) if pd.notna(avg_scale) else float("nan")

#     return {
#         "district": work[COL_DNAME].iloc[0] if not work.empty else district_name,
#         "avg_scale_score": round(avg_scale, 1) if pd.notna(avg_scale) else None,
#         "gap_vs_benchmark": round(gap_vs_benchmark, 1) if pd.notna(gap_vs_benchmark) else None,
#         "tested": tested,
#     }


if __name__ == "__main__":
    print(summarize_district_ela("Alameda Unified"))
