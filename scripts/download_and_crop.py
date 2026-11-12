import zipfile
from pathlib import Path
import numpy as np
import xarray as xr
import cdsapi
import requests
import shutil

# Snakemake passes the injected config automatically
client = cdsapi.Client(
    url=snakemake.config.get("cds_url"),
    key=snakemake.config.get("cds_key")
)

# ===================== EXACT HELPER FUNCTIONS FROM CELL 2 =====================

def ensure_dir(p):
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def unzip_all(zip_path: Path, extract_dir: Path) -> list[Path]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    nc_files = sorted(extract_dir.rglob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"No .nc file found inside zip: {zip_path}")
    return nc_files


def _is_aux_name(p: Path) -> bool:
    n = p.name.lower()
    bad_tokens = ["bounds", "bnds", "vertices", "vertex", "grid", "fx"]
    return any(t in n for t in bad_tokens)


def pick_main_nc(nc_files: list[Path]) -> Path:
    ignore_vars = {
        "bounds_lon", "bounds_lat", "lon_bnds", "lat_bnds", "bnds",
        "lat", "lon", "time", "rlat", "rlon",
        "rotated_pole", "rotated_latitude_longitude", "crs"
    }

    candidates = []
    for f in nc_files:
        if _is_aux_name(f):
            continue
        try:
            with xr.open_dataset(f, decode_times=False) as ds0:
                good = []
                for v in ds0.data_vars:
                    if v in ignore_vars:
                        continue
                    if "time" in ds0[v].dims:
                        good.append(v)
                if good:
                    candidates.append(f)
        except Exception:
            pass

    if candidates:
        return max(candidates, key=lambda p: p.stat().st_size)

    return max(nc_files, key=lambda p: p.stat().st_size)


def find_lat_lon_names(ds: xr.Dataset):
    possible_lat = ["lat", "latitude", "nav_lat"]
    possible_lon = ["lon", "longitude", "nav_lon"]

    lat_name = next((n for n in possible_lat if n in ds.variables), None)
    lon_name = next((n for n in possible_lon if n in ds.variables), None)

    if not lat_name or not lon_name:
        raise KeyError(f"Could not find lat/lon. First vars: {list(ds.variables)[:40]}")

    return lat_name, lon_name


def pick_main_data_var(ds: xr.Dataset, lat: xr.DataArray, lon: xr.DataArray) -> str:
    ignore = {
        "bounds_lon", "bounds_lat", "lon_bnds", "lat_bnds", "bnds",
        "lon", "lat", "time", "height",
        "rlon", "rlat",
        "rotated_pole", "rotated_latitude_longitude",
        "crs"
    }

    grid_dims = tuple(lat.dims)
    cand = []

    for v in ds.data_vars:
        if v in ignore:
            continue
        dims = ds[v].dims
        if "time" not in dims:
            continue
        if all(d in dims for d in grid_dims):
            cand.append(v)

    if cand:
        return cand[0]

    time_vars = [v for v in ds.data_vars if v not in ignore and "time" in ds[v].dims]
    raise ValueError(
        "No main variable found with (time + grid dims).\n"
        f"grid_dims(lat)={grid_dims}\n"
        f"Candidates with time: {time_vars}\n"
        f"All data_vars: {list(ds.data_vars)}"
    )


def crop_to_bbox(
    ds: xr.Dataset,
    varname: str,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float
) -> xr.Dataset:
    lat_name, lon_name = find_lat_lon_names(ds)
    lat = ds[lat_name]
    lon = ds[lon_name]
    da = ds[varname]

    # ---- Case 1: 1D lat/lon ----
    if lat.ndim == 1 and lon.ndim == 1:
        def _slice_1d(coord, vmin, vmax):
            c0 = float(coord.values[0])
            c1 = float(coord.values[-1])
            return slice(vmin, vmax) if c0 <= c1 else slice(vmax, vmin)

        cut = da.sel({
            lat_name: _slice_1d(lat, lat_min, lat_max),
            lon_name: _slice_1d(lon, lon_min, lon_max)
        })

        if cut.size == 0:
            target_lat = (lat_min + lat_max) / 2.0
            target_lon = (lon_min + lon_max) / 2.0

            lat_idx = int(np.abs(lat.values - target_lat).argmin())
            lon_idx = int(np.abs(lon.values - target_lon).argmin())

            cut = da.isel({
                lat_name: slice(lat_idx, lat_idx + 1),
                lon_name: slice(lon_idx, lon_idx + 1)
            })

            print(
                f"⚠️ Το bbox δεν περιείχε grid point. "
                f"Χρησιμοποιείται το κοντινότερο σημείο στο κέντρο του bbox: "
                f"lat={float(lat.values[lat_idx]):.6f}, lon={float(lon.values[lon_idx]):.6f}"
            )

        return cut.to_dataset(name=varname)

    # ---- Case 2: 2D lat/lon (rotated grid) ----
    grid_dims = lat.dims

    if lon.dims != grid_dims:
        raise ValueError(f"lat dims={lat.dims} αλλά lon dims={lon.dims} — δεν ταιριάζουν.")

    if not all(d in da.dims for d in grid_dims):
        raise ValueError(f"The variable '{varname}' does not have the grid dims {grid_dims}. var dims={da.dims}")

    mask = (
        (lat >= lat_min) & (lat <= lat_max) &
        (lon >= lon_min) & (lon <= lon_max)
    )

    mask_stacked = mask.stack(points=grid_dims, create_index=False)
    keep = mask_stacked.compute().values.astype(bool)

    if keep.sum() == 0:
        target_lat = (lat_min + lat_max) / 2.0
        target_lon = (lon_min + lon_max) / 2.0

        dist2 = (lat - target_lat) ** 2 + (lon - target_lon) ** 2
        dist2_stacked = dist2.stack(points=grid_dims, create_index=False)

        nearest_idx = int(np.argmin(dist2_stacked.values))
        keep = np.zeros(dist2_stacked.shape[0], dtype=bool)
        keep[nearest_idx] = True

        nearest_lat = float(lat.stack(points=grid_dims, create_index=False).isel(points=nearest_idx).values)
        nearest_lon = float(lon.stack(points=grid_dims, create_index=False).isel(points=nearest_idx).values)

        print(
            f"⚠️ Το bbox δεν περιείχε grid point. "
            f"Χρησιμοποιείται το κοντινότερο σημείο στο κέντρο του bbox: "
            f"lat={nearest_lat:.6f}, lon={nearest_lon:.6f}"
        )

    da_points = da.stack(points=grid_dims, create_index=False).isel(points=keep)
    lat_points = lat.stack(points=grid_dims, create_index=False).isel(points=keep)
    lon_points = lon.stack(points=grid_dims, create_index=False).isel(points=keep)

    n = int(keep.sum())
    out = xr.Dataset(
        data_vars={varname: da_points},
        coords={
            "points": np.arange(n),
            "lat": ("points", lat_points.values),
            "lon": ("points", lon_points.values),
        }
    )

    if "time" in ds.coords:
        out = out.assign_coords(time=ds["time"])

    return out


def build_cordex_request(start_year, end_year, variable, experiment, params):
    return {
        "domain": params["domain"],
        "experiment": experiment,
        "horizontal_resolution": params["resolution"],
        "temporal_resolution": params["temporal"],
        "variable": [variable],
        "gcm_model": params["gcm"],
        "rcm_model": params["rcm"],
        "ensemble_member": params["ensemble"],
        "year": [str(y) for y in range(start_year, end_year + 1)],
        "month": params["download_months"],
    }


# ===================== SNAKEMAKE EXECUTION BLOCK =====================
def main():
    scenario = snakemake.wildcards.scenario
    variable = snakemake.wildcards.variable
    year_start = int(snakemake.wildcards.year_start)
    year_end = int(snakemake.wildcards.year_end)

    cfg = snakemake.config
    scen_cfg = cfg["scenarios"][scenario]
    experiment = scen_cfg["experiment"]

    work_dir = ensure_dir(snakemake.params.work_dir)
    out_nc = Path(snakemake.output.out_nc)
    ensure_dir(out_nc.parent)

    prefix = f"{variable}_{year_start}_{year_end}"
    zip_path = work_dir / f"{prefix}.zip"

    # Connect to CDS API
    client = cdsapi.Client(url=cfg["cds_url"], key=cfg["cds_key"])

    print(f"Downloading {prefix} for scenario {scenario} ...")
    req = build_cordex_request(year_start, year_end, variable, experiment, cfg)
    client.retrieve(cfg["dataset"], req).download(str(zip_path))

    extract_dir = work_dir / f"_extract_{prefix}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    try:
        nc_files = unzip_all(zip_path, extract_dir)
        nc_path = pick_main_nc(nc_files)
        print(f"Picked NC: {nc_path.name}")

        ds = xr.open_dataset(nc_path, decode_times=True, chunks={"time": 64})
        try:
            lat_name, lon_name = find_lat_lon_names(ds)
            main_var = pick_main_data_var(ds, ds[lat_name], ds[lon_name])
            print(f"Using NetCDF variable: {main_var}")

            cropped = crop_to_bbox(
                ds, main_var,
                cfg["lat_min"], cfg["lat_max"],
                cfg["lon_min"], cfg["lon_max"]
            )

            try:
                cropped.to_netcdf(
                    out_nc,
                    encoding={main_var: {"zlib": True, "complevel": 4}}
                )
            finally:
                cropped.close()

            print(f"Saved: {out_nc}")
        finally:
            ds.close()

    finally:
        if not cfg.get("keep_zip", False):
            zip_path.unlink(missing_ok=True)
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

if __name__ == "__main__":
    main()