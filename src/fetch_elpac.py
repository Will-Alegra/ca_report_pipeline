import os, re
import pandas as pd
from pathlib import Path

ELPAC_PATH = "data_raw/elpac_2024_summative.txt"



BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ELPAC_PATH = BASE_DIR / "data_raw" / "elpac_2024_summative.txt"

def _read_elpac(filepath: str | None):
    path = Path(filepath) if filepath else DEFAULT_ELPAC_PATH
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Save the statewide Summative ELPAC research file there.")
    # ELPAC research file is caret-delimited
    return pd.read_csv(path, sep="^", engine="python", header=0, dtype=str, encoding="latin1")

def list_districts(filepath: str | None = None, limit: int = 50):
    df = _read_elpac(filepath)
    # Try both possible headers
    dcol = "DistrictName" if "DistrictName" in df.columns else (
        "District Name" if "District Name" in df.columns else None
    )
    if dcol is None:
        raise ValueError(f"Could not find a district name column. Columns are: {list(df.columns)}")
    return sorted(df[dcol].dropna().unique())[:limit]



def district_elpac_speaking_pct_below_by_grade(district_name: str, filepath: str | None = None):
    """
    Returns (labels, pct_below, tested) for grades 1–5 where:
      pct_below = SpeakingDomainBegin + SpeakingDomainModerate
                  (as percent of total speaking domain students for the grade).
    Uses district-level rows (SchoolCode 0/0000000), picks the row with the
    largest SpeakingDomainTotal per grade when duplicates exist.
    """
    df = _read_elpac(filepath)

    # Column aliases present in the statewide file
    COL_DNAME    = "DistrictName" if "DistrictName" in df.columns else "District Name"
    COL_SCODE    = "SchoolCode"   if "SchoolCode"   in df.columns else "School Code"
    COL_GRADE    = "Grade"
    COL_TOT      = "SpeakingDomainTotal"
    # percentages, if present
    COL_P1_PCT   = "SpeakingDomainBeginPcnt"
    COL_P2_PCT   = "SpeakingDomainModeratePcnt"
    # counts, as fallback
    COL_P1_CNT   = "SpeakingDomainBeginCount"
    COL_P2_CNT   = "SpeakingDomainModerateCount"

    needed = [COL_DNAME, COL_SCODE, COL_GRADE, COL_TOT]
    miss = [c for c in needed if c not in df.columns]
    if miss:
        raise ValueError(f"ELPAC: missing columns {miss}\nHave: {list(df.columns)}")

    # --- district match (tolerant of “School District” suffix) ---
    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
    target = norm(district_name).lower()
    work = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)].copy()
    if work.empty:
        raise ValueError(f"No ELPAC rows found for district containing '{district_name}'.")

    # --- district-level only ---
    sc = work[COL_SCODE].astype(str).str.strip()
    work = work[(sc == "0") | (sc == "0000000")].copy()
    if work.empty:
        raise ValueError("Found district, but no district-level rows (SchoolCode == 0000000).")

    # --- keep 1–5 for our axis ---
    work[COL_GRADE] = work[COL_GRADE].astype(str).str.strip()
    work = work[work[COL_GRADE].isin(["01","1","02","2","03","3","04","4","05","5"])].copy()

    # normalize grade labels to '1'..'5'
    def gnorm(x: str) -> str:
        x = x.strip()
        return x[-1] if x in {"01","02","03","04","05"} else x
    work["__G"] = work[COL_GRADE].map(gnorm)

    # numeric coercions
    to_num = lambda s: pd.to_numeric(s, errors="coerce")
    work[COL_TOT] = to_num(work[COL_TOT]).fillna(0).astype(int)

    have_pct = (COL_P1_PCT in work.columns) and (COL_P2_PCT in work.columns)
    if have_pct:
        work[COL_P1_PCT] = to_num(work[COL_P1_PCT])
        work[COL_P2_PCT] = to_num(work[COL_P2_PCT])
    else:
        # counts fallback if needed
        if (COL_P1_CNT in work.columns) and (COL_P2_CNT in work.columns):
            work[COL_P1_CNT] = to_num(work[COL_P1_CNT]).fillna(0).astype(int)
            work[COL_P2_CNT] = to_num(work[COL_P2_CNT]).fillna(0).astype(int)

    # choose the row with largest total per grade
    work = work.sort_values(["__G", COL_TOT], ascending=[True, False]).drop_duplicates(subset=["__G"], keep="first")

    axis = ["1","2","3","4","5"]
    pct_map  = {g: None for g in axis}
    test_map = {g: 0    for g in axis}

    for _, r in work.iterrows():
        g = r["__G"]
        if g not in pct_map:
            continue
        test_map[g] = int(r[COL_TOT])

        if have_pct and pd.notna(r[COL_P1_PCT]) and pd.notna(r[COL_P2_PCT]):
            pct_map[g] = float(r[COL_P1_PCT]) + float(r[COL_P2_PCT])
        else:
            # compute from counts if possible
            if (COL_P1_CNT in work.columns) and (COL_P2_CNT in work.columns) and r[COL_TOT] > 0:
                pct_map[g] = 100.0 * (float(r[COL_P1_CNT]) + float(r[COL_P2_CNT])) / float(r[COL_TOT])

    labels    = axis
    pct_below = [pct_map[g]  for g in axis]
    tested    = [test_map[g] for g in axis]
    return labels, pct_below, tested


def district_elpac_speaking_by_grade(district_name: str, filepath: str = ELPAC_PATH):
    """
    Returns (labels, values, tested) for grades 1–5 using ELPAC Speaking domain.
    Value = weighted average performance level (1–3).
    Uses district-level rows (SchoolCode == 0/0000000).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Missing {filepath}. Save the statewide Summative ELPAC research file there.")

    # This file uses caret-delimited, camelCase headers.
    df = pd.read_csv(filepath, sep="^", engine="python", header=0, dtype=str, encoding="latin1")

    # Column names in your file (from your traceback)
    COL_DNAME   = "DistrictName"
    COL_SCODE   = "SchoolCode"
    COL_GRADE   = "Grade"

    # Speaking domain level counts & total
    COL_BEGIN   = "SpeakingDomainBeginCount"
    COL_MOD     = "SpeakingDomainModerateCount"
    COL_DEV     = "SpeakingDomainDevelopedCount"
    COL_TOTAL   = "SpeakingDomainTotal"

    required = [COL_DNAME, COL_SCODE, COL_GRADE, COL_BEGIN, COL_MOD, COL_DEV, COL_TOTAL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"ELPAC: missing columns {missing}\nHave: {list(df.columns)}")

    # Filter to target district (tolerant re: 'School District' suffix)
    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s or "").strip(), flags=re.I)
    target = norm(district_name).lower()
    work = df[df[COL_DNAME].astype(str).str.lower().str.contains(target, na=False)].copy()
    if work.empty:
        raise ValueError(f"No ELPAC rows found for district containing '{district_name}'.")

    # District-level rows only
    if "TypeID" in work.columns:
        tid = work["TypeID"].astype(str).str.strip().str.upper()
        # '02' is district-level in your file; keep 'D'/'DISTRICT' for other vintages.
        work = work[tid.isin(["02", "D", "DISTRICT"])].copy()
    else:
        sc = work["SchoolCode"].astype(str).str.strip()
        work = work[(sc == "0") | (sc == "0000000")].copy()

    print("[elpac] rows after district filter:", len(work))  # debug
    if work.empty:
        raise ValueError("Found district, but no district-level rows after TypeID/SchoolCode filter.")


    
    #debug for what nameing scheme elpac uses
    # print("[elpac] candidates for district:", sorted(work["DistrictName"].unique())[:5])

    # # See what aggregate levels we have; ELPAC uses TypeID like 'D' (district) / 'S' (school)
    # if "TypeID" in work.columns:
    #     print("[elpac] TypeID uniques:", work["TypeID"].astype(str).unique())

    # # Peek which grades exist and where the speaking totals are nonzero
    # if "SpeakingDomainTotal" in work.columns:
    #     tmp = work.copy()
    #     tmp["GradeNorm"] = tmp["Grade"].astype(str).str.strip().str.replace("^0", "", regex=True)
    #     nonzero = tmp[tmp["SpeakingDomainTotal"].astype(str) != "0"]
    #     print("[elpac] grade sample (nonzero SpeakingDomainTotal):",
    #         nonzero[["Grade", "GradeNorm", "SpeakingDomainTotal"]].head(10).to_dict(orient="records"))


    # Keep grades 1–5 only (consistent x-axis) — normalize '01' -> '1'
    axis = ["1", "2", "3", "4", "5"]
    work["GradeNorm"] = (
        work[COL_GRADE]
        .astype(str)
        .str.strip()
        .str.replace(r"^0", "", regex=True)  # remove a single leading zero
    )
    work = work[work["GradeNorm"].isin(axis)].copy()

    # Coerce to numeric
    for c in [COL_BEGIN, COL_MOD, COL_DEV, COL_TOTAL]:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0).astype(int)

    # If multiple rows per grade, keep the one with largest SpeakingDomainTotal
    work = work.sort_values(["GradeNorm", COL_TOTAL], ascending=[True, False]) \
               .drop_duplicates(subset=["GradeNorm"], keep="first")

    # Compute avg level per grade (1..3)
    values_by_grade = {g: None for g in axis}
    tested_by_grade = {g: 0    for g in axis}

    for _, r in work.iterrows():
        g = r["GradeNorm"]
        total = int(r[COL_TOTAL])
        if total > 0:
            begin = int(r[COL_BEGIN])
            moderate = int(r[COL_MOD])
            developed = int(r[COL_DEV])
            avg_level = (1*begin + 2*moderate + 3*developed) / total
            values_by_grade[g] = float(avg_level)
            tested_by_grade[g] = total

    labels = axis
    values = [values_by_grade[g] for g in labels]
    tested = [tested_by_grade[g] for g in labels]
    print("[debug] ELPAC speaking by grade:", list(zip(labels, values)))  # debug
    return labels, values, tested

def load_elpac(filepath: str | None = None):
    """Public wrapper for reading the full ELPAC dataset."""
    return _read_elpac(filepath)


