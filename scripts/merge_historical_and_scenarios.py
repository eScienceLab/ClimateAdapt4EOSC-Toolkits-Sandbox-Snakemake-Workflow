import sys
from pathlib import Path
import re
import numpy as np
import xarray as xr

FILE_RE = re.compile(
    r"^annual_(mean|sum)_(.+)-(\d{4})-(\d{4})(?:_rcp_(?:45|85))?\.nc$"
)

def parse_annual_filename(path: Path):
    m = FILE_RE.match(path.name)
    if not m:
        return None
    return {
        "path": path,
        "aggregation": m.group(1),
        "variable_label": m.group(2),
        "start_year": int(m.group(3)),
        "end_year": int(m.group(4)),
        "key": (m.group(1), m.group(2)),
    }

def scan_annual_files(folder: Path):
    if not folder.exists():
        return []
    records = []
    for p in sorted(folder.glob("annual_*.nc")):
        rec = parse_annual_filename(p)
        if rec is not None:
            records.append(rec)
    return records

def detect_annual_dim(ds: xr.Dataset) -> str:
    if "year" in ds.dims or "year" in ds.coords:
        return "year"
    if "time" in ds.dims or "time" in ds.coords:
        return "time"
    raise ValueError("❌ Neither 'year' nor 'time' dimension found in dataset.")

def open_and_prepare(path: Path) -> xr.Dataset:
    ds = xr.open_dataset(path, decode_times=True)
    if len(ds.data_vars) == 0:
        ds.close()
        raise ValueError(f"❌ No data variables in: {path}")
    detect_annual_dim(ds)
    ds = ds.load()
    ds.attrs = dict(ds.attrs)
    ds.attrs["source_file"] = path.name
    return ds

def sort_and_remove_duplicate_years(ds: xr.Dataset) -> xr.Dataset:
    annual_dim = detect_annual_dim(ds)
    ds = ds.sortby(annual_dim)
    values = ds[annual_dim].values
    _, unique_idx = np.unique(values, return_index=True)
    unique_idx = np.sort(unique_idx)
    return ds.isel({annual_dim: unique_idx})

def merge_file_records(records):
    records = sorted(records, key=lambda r: (r["start_year"], r["end_year"]))
    datasets = []
    try:
        for rec in records:
            ds = open_and_prepare(rec["path"])
            datasets.append(ds)
        annual_dim = detect_annual_dim(datasets[0])
        merged = xr.concat(
            datasets, dim=annual_dim, coords="minimal", compat="override", join="outer"
        )
        return sort_and_remove_duplicate_years(merged)
    finally:
        for ds in datasets:
            try:
                ds.close()
            except Exception:
                pass

def main():
    scenario = snakemake.wildcards.scenario
    aggregation = snakemake.wildcards.agg_type
    variable_label = snakemake.wildcards.variable

    # Correctly point to the scenario subfolder where annual files live
    scenario_dir = Path(snakemake.params.scenario_dir) / scenario
    hist_dir = Path(snakemake.params.hist_dir)
    out_path = Path(snakemake.output.final_nc)
    
    # ... rest of the script stays exactly the same ...

    print(f"\n🌍 Merging historical + scenario for {scenario} [{aggregation}_{variable_label}]...")

    hist_records = scan_annual_files(hist_dir)
    hist_by_key = {rec["key"]: [] for rec in hist_records}
    for rec in hist_records:
        hist_by_key[rec["key"]].append(rec)

    scenario_records = scan_annual_files(scenario_dir)
    scen_by_key = {}
    for rec in scenario_records:
        scen_by_key.setdefault(rec["key"], []).append(rec)

    key = (aggregation, variable_label)
    scen_recs = scen_by_key.get(key, [])
    if not scen_recs:
        raise FileNotFoundError(f"❌ No annual records found for {key} in {scenario_dir}")

    combined_records = hist_by_key.get(key, []) + scen_recs
    combined_records = sorted(combined_records, key=lambda r: (r["start_year"], r["end_year"]))

    merged = merge_file_records(combined_records)

    start_year = min(r["start_year"] for r in combined_records)
    end_year = max(r["end_year"] for r in combined_records)
    
    merged.attrs["scenario"] = scenario
    merged.attrs["periods"] = "_".join([f"{r['start_year']}-{r['end_year']}" for r in combined_records])
    merged.attrs["filename_period"] = f"{start_year}-{end_year}"

    encoding = {var: {"zlib": True, "complevel": 4} for var in merged.data_vars}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_netcdf(out_path, encoding=encoding)
    merged.close()

    print(f"✅ Saved final merged file: {out_path}")

if __name__ == "__main__":
    main()