# src/fetch_caaspp.py
import os
import re
import pandas as pd
from pathlib import Path

# Default location for the statewide CAASPP file
BASE_DIR = Path(__file__).resolve().parents[1]          # project root
DEFAULT_CAASPP_PATH = BASE_DIR / "data_raw" / "caaspp_2024_ela.txt"


BENCHMARK_DEFAULT = 2500.0  # “Standard Met” scale-score cut near 2500 for ELA

def _read_caaspp(filepath: str | None = None) -> pd.DataFrame:
    """
    Read the CAASPP ELA research file (caret-delimited) with robust path handling.
    """
    path = Path(filepath) if filepath else DEFAULT_CAASPP_PATH
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Put the CAASPP ELA research file there.")
    return pd.read_csv(path, sep="^", engine="python", header=0, dtype=str, encoding="latin1")

def load_caaspp(filepath: str | None = None) -> pd.DataFrame:
    """Public wrapper so you can import and quickly inspect districts, etc."""
    return _read_caaspp(filepath)

def list_districts(filepath: str | None = None, limit: int = 50):
    df = _read_caaspp(filepath)
    dcol = "District Name" if "District Name" in df.columns else (
        "DistrictName" if "DistrictName" in df.columns else None
    )
    if dcol is None:
        raise ValueError(f"Could not find a district name column. Columns are: {list(df.columns)}")
    return sorted(df[dcol].dropna().unique())[:limit]



def fetch_caaspp_ela_gap(
    district_name: str,
    filepath: str | None = None,
    benchmark_scale_score: float = BENCHMARK_DEFAULT,
):
    """
    Reads the CAASPP ELA research file (caret-delimited) using the 2024 header names you showed,
    filters to district-level rows for the chosen district, picks the 'All Students' row per grade
    by taking the record with the largest tested count, and returns a weighted average and gap.

    Returns: dict {district, avg_scale_score, gap, tested}
    """
    # Use the common reader (handles defaults + paths)
    df = _read_caaspp(filepath)

    COL_DNAME  = "District Name"
    COL_SNAME  = "School Name"
    COL_SCODE  = "School Code"
    COL_GRADE  = "Grade"
    COL_TESTED = ("Total Students Tested with Scores"
                  if "Total Students Tested with Scores" in df.columns
                  else "Total Students Tested")
    COL_AVG    = "Mean Scale Score"

    # Map the exact column names from your error message
    COL_DNAME  = "District Name"
    COL_SNAME  = "School Name"
    COL_SCODE  = "School Code"
    COL_GRADE  = "Grade"
    # Prefer 'Total Students Tested with Scores' else fallback to 'Total Students Tested'
    COL_TESTED = "Total Students Tested with Scores" if "Total Students Tested with Scores" in df.columns \
                 else "Total Students Tested"
    COL_AVG    = "Mean Scale Score"

    required = [COL_DNAME, COL_SCODE, COL_GRADE, COL_TESTED, COL_AVG]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing from CAASPP file: {missing}\nHave: {list(df.columns)}")

    # 1) Filter to the chosen district (tolerant match; strip 'School District' suffix)
    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
    target = norm(district_name).lower()
    df = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)]
    if df.empty:
        raise ValueError(f"No CAASPP rows found for district name containing '{district_name}'.")

    # 2) District-level rows only: CAASPP uses 0000000 as the district row (no school)
    #    Keep strings for codes; treat '0000000' and numeric 0 both as district-level
    scode = df[COL_SCODE].astype(str).str.strip()
    is_district_level = (scode == "0") | (scode == "0000000")
    df = df[is_district_level]
    if df.empty:
        raise ValueError("Found the district, but no district-level rows (School Code == 0000000).")

    # 3a) Coerce numerics
    df[COL_TESTED] = pd.to_numeric(df[COL_TESTED], errors="coerce").fillna(0).astype(int)
    df[COL_AVG]    = pd.to_numeric(df[COL_AVG], errors="coerce")

    # 3b) LOCK to All Students group (from your debug: Student Group ID == 1)
    SG_COL = "Student Group ID"
    if SG_COL in df.columns:
        df = df[df[SG_COL].astype(str).str.strip() == "1"]

    # 3c) Exclude the “All grades” rollup row (grade 13), keep tested grades (3–8, 11)
    valid_grades = {"3", "4", "5", "6", "7", "8", "11"}
    df[COL_GRADE] = df[COL_GRADE].astype(str).str.strip()
    df = df[df[COL_GRADE].isin(valid_grades)]

    # --- DEBUG: peek which groups exist at district level and their tested totals
    # SG_COL = "Student Group ID" if "Student Group ID" in df.columns else None
    # if SG_COL:
    #     print("[debug] District-level groups by tested count (top 10):")
    #     print(
    #         df.groupby(SG_COL)[COL_TESTED].sum()
    #         .sort_values(ascending=False)
    #         .head(10)
    #         .to_string()
    #     )
    #     # also show a few rows for the top group to see if scores look ~2400–2600
    #     top_group = (
    #         df.groupby(SG_COL)[COL_TESTED].sum().sort_values(ascending=False).index[0]
    #     )
    #     print(f"[debug] sample rows for group {top_group}:")
    #     print(
    #         df[df[SG_COL] == top_group][[COL_GRADE, COL_TESTED, COL_AVG]]
    #         .head(8)
    #         .to_string(index=False)
    #     )


    # 4) For each grade, keep the row with the **largest tested** -> best proxy for 'All Students'
    #    This avoids needing a specific 'Student Group ID' code.
    df = df.sort_values([COL_GRADE, COL_TESTED], ascending=[True, False])
    df = df.drop_duplicates(subset=[COL_GRADE], keep="first")

    # 5) Weighted average across grades
    tested_total = int(df[COL_TESTED].sum())
    weighted_sum = float((df[COL_AVG] * df[COL_TESTED]).sum())
    avg_scale_score = (weighted_sum / tested_total) if tested_total > 0 else float("nan")

    gap = float(benchmark_scale_score - avg_scale_score) if pd.notna(avg_scale_score) else float("nan")

    # Use a clean district name from the remaining rows (they should all match)
    district_clean = df[COL_DNAME].iloc[0] if not df.empty else district_name

    return {
        "district": district_clean,
        "avg_scale_score": round(avg_scale_score, 1) if pd.notna(avg_scale_score) else None,
        "gap": round(gap, 1) if pd.notna(gap) else None,
        "tested": tested_total,
    }

if __name__ == "__main__":
    print(fetch_caaspp_ela_gap("Alameda Unified"))
