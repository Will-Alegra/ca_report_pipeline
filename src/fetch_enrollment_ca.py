import os
import re
import pandas as pd
from pandas.api.types import is_numeric_dtype
from pathlib import Path

def _read_tsv(filepath):
    # Try TSV first (common for the statewide demo-downloads)
    return pd.read_csv(filepath, sep="\t", header=0, encoding="latin1", engine="python")

def _read_fwf(filepath):
    return pd.read_fwf(filepath, header=None, encoding="latin1")

def fetch_enrollment_school_row(school_name: str, filepath: str = "data_raw/cdenroll2425.txt"):
    """
    Return a single-row DataFrame shaped like:
      School | K | 1 | 2 | 3 | 4 | 5 | Total
    for the given SCHOOL (case-insensitive). Works on the statewide TSV.
    """
    # --- read exactly like your district function does
    df = _read_tsv(filepath)
    if df.shape[1] <= 2:
        df = _read_fwf(filepath)

    required = [
        "AcademicYear","AggregateLevel","CountyCode","DistrictCode","SchoolCode",
        "CountyName","DistrictName","SchoolName","Charter","ReportingCategory",
        "TOTAL_ENR","GR_TK","GR_KN","GR_01","GR_02","GR_03","GR_04","GR_05",
        "GR_06","GR_07","GR_08","GR_09","GR_10","GR_11","GR_12"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Expected headers missing from TSV: {missing}")

    work = df.copy()

    # filter by school name (contains, case-insensitive), then prefer exact match
    target = str(school_name).strip().lower()
    cand = work[work["SchoolName"].astype(str).str.lower().str.contains(target, na=False)].copy()
    if cand.empty:
        raise ValueError(f"No rows found for school containing '{school_name}'.")

    exact_mask = cand["SchoolName"].astype(str).str.strip().str.lower().eq(target)
    if exact_mask.any():
        cand = cand[exact_mask].copy()

    # choose “All Students” row for that school by taking the largest TOTAL_ENR
    cand["TOTAL_ENR"] = pd.to_numeric(cand["TOTAL_ENR"], errors="coerce").fillna(0)
    idx = cand["TOTAL_ENR"].idxmax()
    row = cand.loc[[idx]]

    # build K–5 output
    out = row[["SchoolName","GR_KN","GR_01","GR_02","GR_03","GR_04","GR_05"]].copy()
    out = out.rename(columns={
        "SchoolName":"School",
        "GR_KN":"K","GR_01":"1","GR_02":"2","GR_03":"3","GR_04":"4","GR_05":"5",
    })
    for g in ["K","1","2","3","4","5"]:
        out[g] = pd.to_numeric(out[g], errors="coerce").fillna(0).astype(int)
    out["Total"] = out[["K","1","2","3","4","5"]].sum(axis=1)

    return out.reset_index(drop=True)


def fetch_enrollment_from_txt(district_name, filepath=None, include_charters=True):
    """
    Load the statewide enrollment file and filter to one district.
    If `filepath` is None or a relative path, resolve it relative to the project root.
    """
    # project root = one level up from src/
    BASE_DIR = Path(__file__).resolve().parents[1]

    # default file location
    if filepath is None:
        filepath = BASE_DIR / "data_raw" / "cdenroll2425.txt"
    else:
        filepath = Path(filepath)
        if not filepath.is_absolute():
            filepath = BASE_DIR / filepath

    if not filepath.exists():
        raise FileNotFoundError(f"Missing {filepath}. Save cdenroll2425.txt into data_raw/.")

    # --- 1) Read as TSV first; if it looks like 1-2 columns only, try FWF
    df = _read_tsv(filepath)
    if df.shape[1] <= 2:
        df = _read_fwf(filepath)
    print("[debug] shape:", df.shape)
    print("[debug] tail column names:", list(df.columns[-25:]))


    col_count = df.shape[1]

    # Two schema paths:
    # A) WIDE TSV: many columns (>= 20) with grade counts at the end
    # B) NARROW FWF/TSV: ~12-14 columns with one Enroll column + a Grade code

    # -----------------------
    # A) WIDE TSV HANDLER (exact headers from your file)
    # -----------------------
    if col_count >= 20:
        # We already read with header=0, so columns are real names.
        required = [
            "AcademicYear", "AggregateLevel", "CountyCode", "DistrictCode", "SchoolCode",
            "CountyName", "DistrictName", "SchoolName", "Charter", "ReportingCategory",
            "TOTAL_ENR", "GR_TK", "GR_KN", "GR_01", "GR_02", "GR_03", "GR_04", "GR_05",
            "GR_06", "GR_07", "GR_08", "GR_09", "GR_10", "GR_11", "GR_12"
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Expected headers missing from TSV: {missing}")

        work = df.copy()

        # DEBUG: show what the file actually calls the district(s) that include "alameda"
        mask_alameda = work["DistrictName"].astype(str).str.contains("alameda", case=False, na=False)
        print("[debug] possible district names containing 'alameda':",
            sorted(work.loc[mask_alameda, "DistrictName"].astype(str).unique())[:20])


        # 1) District filter (contains, case-insensitive; strip 'School District' suffix if you like)
        import re
        norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s).strip(), flags=re.I)
        target = norm(district_name).lower()
        work = work[work["DistrictName"].astype(str).str.lower().str.contains(target, na=False)]

        #one time debugger
        print("[debug] AggregateLevel uniques:", sorted(work["AggregateLevel"].astype(str).unique())[:20])


       # 2) School-level only (tolerant) — some files use "School", others use "S", etc.
        if "AggregateLevel" in work.columns:
            agg = work["AggregateLevel"].astype(str).str.lower()
            mask_school = agg.isin(["school", "s", "schl"])
        else:
            mask_school = pd.Series([True] * len(work), index=work.index)

        # Fallback: if that yields nothing, use presence of a non-empty SchoolName
        if mask_school.sum() == 0:
            mask_school = work["SchoolName"].astype(str).str.strip().ne("")

        work = work[mask_school]
        #debuger
        print("[debug] rows after school-level filter:", len(work))

        # Optional: exclude charters if requested (column is "Charter": 'Y'/'N')
        if not include_charters and "Charter" in work.columns:
            work = work[work["Charter"].astype(str).str.upper().ne("Y")]






        # 3) Pick the "All Students"-equivalent row per school by taking the row with the largest TOTAL_ENR
        #    (subgroups are always <= total). This avoids relying on ReportingCategory labels like 'TA'.
        work = work.copy()
        work["TOTAL_ENR"] = pd.to_numeric(work["TOTAL_ENR"], errors="coerce").fillna(0)
        idx = work.groupby("SchoolName")["TOTAL_ENR"].idxmax()
        work = work.loc[idx]
        #---debug printing----
        print("[debug] rows after TOTAL_ENR pick:", len(work))


        # 4) Build K–5 columns
        out = work[["SchoolName", "GR_KN", "GR_01", "GR_02", "GR_03", "GR_04", "GR_05"]].copy()
        out.rename(columns={
            "SchoolName": "School",
            "GR_KN": "K", "GR_01": "1", "GR_02": "2",
            "GR_03": "3", "GR_04": "4", "GR_05": "5",
        }, inplace=True)

        # 5) Coerce numeric and compute Total
        for g in ["K", "1", "2", "3", "4", "5"]:
            out[g] = pd.to_numeric(out[g], errors="coerce").fillna(0).astype(int)
        out["Total"] = out[["K", "1", "2", "3", "4", "5"]].sum(axis=1)

        # 6) Sort nicely
        out = out.sort_values("School").reset_index(drop=True)

        if out.empty:
            raise ValueError("Wide TSV parsed, but no K–5 rows after filtering. Check district name or ReportingCategory.")
        return out
    # -----------------------
    # B) NARROW FWF/TSV HANDLER (previous logic)
    # -----------------------
    # Assign names for ~12–14 cols
    if col_count == 14:
        df.columns = [
            "Year", "AggLevel", "CountyCode", "DistrictCode", "SchoolCode",
            "CharterYN", "ReportingCategory", "Grade", "Enroll",
            "CountyName", "DistrictName", "SchoolName", "Extra1", "Extra2"
        ]
    elif col_count == 12:
        df.columns = [
            "Year", "Type", "CountyCode", "DistrictCode", "SchoolCode",
            "CountyName", "DistrictName", "SchoolName", "CharterYN",
            "SubgroupID", "Grade", "Enroll"
        ]
    else:
        df.columns = [f"C{i}" for i in range(col_count)]

    if "DistrictName" not in df.columns:
        raise ValueError(f"Couldn't find DistrictName in columns: {list(df.columns)}")

    norm = lambda s: re.sub(r"\s+school\s+district$", "", str(s).strip(), flags=re.I)
    target = norm(district_name).lower()
    df = df[df["DistrictName"].astype(str).str.lower().str.contains(target, na=False)]

    if "AggLevel" in df.columns:
        df = df[df["AggLevel"].astype(str).str.upper().str.startswith("S")]

    # prefer All Students if label exists
    if "ReportingCategory" in df.columns:
        pref = df[df["ReportingCategory"].astype(str).str.upper().eq("TA")]
        if not pref.empty:
            df = pref
    elif "SubgroupID" in df.columns:
        pref = df[df["SubgroupID"].fillna(-1).astype(int).eq(0)]
        if not pref.empty:
            df = pref

    # Keep K–5 grades
    if "Grade" not in df.columns:
        raise ValueError("Couldn't find Grade column.")
    df = df[df["Grade"].isin(["KN", "01", "02", "03", "04", "05"])]

    # Ensure Enroll
    if "Enroll" not in df.columns:
        num_cols = [c for c in df.columns if is_numeric_dtype(df[c])]
        if not num_cols:
            raise ValueError("Couldn't find numeric Enroll column.")
        df = df.rename(columns={num_cols[-1]: "Enroll"})

    # Pivot
    wide = df.pivot(index="SchoolName", columns="Grade", values="Enroll").fillna(0).astype(int)
    wide = wide.rename(columns={"KN": "K", "01": "1", "02": "2", "03": "3", "04": "4", "05": "5"})
    for g in ["K", "1", "2", "3", "4", "5"]:
        if g not in wide.columns:
            wide[g] = 0
    wide["Total"] = wide[["K", "1", "2", "3", "4", "5"]].sum(axis=1)
    out = wide.reset_index().rename(columns={"SchoolName": "School"})
    out = out[["School", "K", "1", "2", "3", "4", "5", "Total"]].sort_values("School").reset_index(drop=True)

    if out.empty:
        raise ValueError("Parsed narrow file but got no rows after filtering K–5.")
    return out
