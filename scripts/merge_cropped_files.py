import sys
from pathlib import Path
import re
import numpy as np
import xarray as xr


def find_cropped_files_for_period(out_dir: Path, variable: str, start_year: int, end_year: int):
    pattern = re.compile(rf"^{re.escape(variable)}_(\d{{4}})_(\d{{4}})_CROPPED\.nc$")
    selected = []

    print(f"Searching in {out_dir} for variable '{variable}' matching pattern...")
    for p in sorted(out_dir.glob(f"{variable}_*_CROPPED.nc")):
        m = pattern.match(p.name)
        if not m:
            continue

        file_start = int(m.group(1))
        file_end = int(m.group(2))

        if file_end >= start_year and file_start <= end_year:
            selected.append((file_start, file_end, p))

    if not selected:
        raise FileNotFoundError(
            f"No cropped files found for variable {variable} "
            f"that overlap with period {start_year}-{end_year} in {out_dir}."
        )

    selected.sort(key=lambda x: x[0])
    return selected


def subset_exact_time(ds: xr.Dataset, start_year: int, end_year: int) -> xr.Dataset:
    if "time" not in ds.coords:
        raise ValueError("Dataset has no 'time' coordinate.")

    start_date = np.datetime64(f"{start_year}-01-01")
    end_date = np.datetime64(f"{end_year}-12-31")

    out = ds.sel(time=slice(start_date, end_date))

    if out.sizes.get("time", 0) == 0:
        raise ValueError(
            f"After time subset, no time steps remained for {start_year}-{end_year}."
        )

    return out


def main():
    final_path = Path(snakemake.output.final_nc)
    out_dir = final_path.parent
    variable = snakemake.wildcards.variable
    start_year = int(snakemake.wildcards.year_start)
    end_year = int(snakemake.wildcards.year_end)

    print(f"\n{'=' * 60}")
    print(f"Merging variable: {variable} for period {start_year}-{end_year}")
    print(f"Target output: {final_path}")
    print(f"{'=' * 60}")

    selected = find_cropped_files_for_period(out_dir, variable, start_year, end_year)

    print("Cropped files to be merged:")
    for s, e, p in selected:
        print(f"  - {p.name} [{s}-{e}]")

    datasets = []
    merged = None

    try:
        for _, _, p in selected:
            print(f"Opening dataset: {p}")
            ds = xr.open_dataset(p, decode_times=True)
            datasets.append(ds)

        print("Concatenating datasets along time...")
        merged = xr.concat(datasets, dim="time")
        merged = merged.sortby("time")

        # Remove duplicate timestamps, if any.
        if "time" in merged.coords:
            _, unique_idx = np.unique(
                merged["time"].values, return_index=True
            )
            unique_idx = np.sort(unique_idx)
            merged = merged.isel(time=unique_idx)

        # Keep only the requested years.
        print(f"Subsetting exact time window: {start_year} to {end_year}...")
        merged = subset_exact_time(merged, start_year, end_year)

        data_vars = list(merged.data_vars)
        if not data_vars:
            raise ValueError(f"No data variables found for {variable}.")

        main_var = data_vars[0]
        print(f"Main data variable identified: {main_var}")

        encoding = {main_var: {"zlib": True, "complevel": 4}}
        
        print(f"Writing final NetCDF to {final_path}...")
        merged.to_netcdf(final_path, encoding=encoding)

        # Explicit verification
        if final_path.exists():
            print(f"SUCCESS: Created final file: {final_path} ({final_path.stat().st_size} bytes)")
        else:
            raise RuntimeError(f"FAILED: Expected file {final_path} was not created.")

    finally:
        if merged is not None:
            try:
                merged.close()
            except Exception:
                pass

        for ds in datasets:
            try:
                ds.close()
            except Exception:
                pass

    print("\nMerging completed successfully.")


if __name__ == "__main__":
    main()