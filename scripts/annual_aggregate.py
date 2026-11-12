import sys
from pathlib import Path
import numpy as np
import xarray as xr

KELVIN_TO_C = 273.15

def open_ds(nc_path: Path) -> xr.Dataset:
    ds = xr.open_dataset(nc_path, decode_times=True)
    if len(ds.data_vars) == 0:
        ds.close()
        raise ValueError(f"❌ No data_vars found in: {nc_path}")
    if "time" not in ds.coords and "time" not in ds.dims:
        ds.close()
        raise ValueError(f"❌ Could not find 'time' dimension/coordinate in: {nc_path}")
    return ds

def is_temperature_var(var_name: str, da: xr.DataArray) -> bool:
    units = str(da.attrs.get("units", "")).strip().lower()
    stdn = str(da.attrs.get("standard_name", "")).lower()
    lnam = str(da.attrs.get("long_name", "")).lower()
    name = var_name.lower()

    if units in {"k", "kelvin"}:
        return True
    if "temperature" in stdn or "temperature" in lnam:
        return True
    if any(tok in name for tok in ["temp", "temperature", "tas"]):
        return True
    return False

def convert_temperature_k_to_c(da: xr.DataArray) -> xr.DataArray:
    out = da - KELVIN_TO_C
    out.attrs = dict(da.attrs)
    out.attrs["units"] = "C"
    out.attrs["long_name"] = out.attrs.get("long_name", "Temperature") + " (converted to Celsius)"
    return out

def convert_precip_flux_to_mm_per_timestep(da: xr.DataArray) -> xr.DataArray:
    out = (da * 86400).astype("float32")
    out.attrs = dict(da.attrs)
    out.attrs["units"] = "mm/day"
    out.attrs["long_name"] = "Daily precipitation amount derived from mean precipitation flux"
    return out

def main():
    input_path = Path(snakemake.input.nc_file)
    output_path = Path(snakemake.output.annual_nc)
    variable = snakemake.wildcards.variable
    is_precip = (variable == "mean_precipitation_flux")

    print(f"Aggregating annually for {variable} from {input_path}...")

    ds = open_ds(input_path)
    out_vars = {}

    for var_name, da in ds.data_vars.items():
        if is_precip:
            da2 = convert_precip_flux_to_mm_per_timestep(da)
            annual = da2.groupby("time.year").sum("time", skipna=True)
            annual.attrs = dict(da2.attrs)
            annual.attrs["units"] = "mm/year"
            annual.attrs["long_name"] = annual.attrs.get("long_name", "Precipitation") + " (annual total)"
        else:
            da2 = da
            if is_temperature_var(var_name, da2):
                units = str(da2.attrs.get("units", "")).strip().lower()
                if units in {"k", "kelvin"}:
                    da2 = convert_temperature_k_to_c(da2)
            annual = da2.groupby("time.year").mean("time", skipna=True)
            annual.attrs = dict(da2.attrs)

        annual.name = var_name
        out_vars[var_name] = annual

    out_ds = xr.Dataset(out_vars)
    out_ds.attrs = dict(ds.attrs)
    out_ds.to_netcdf(output_path)
    ds.close()

    print(f"✅ Saved annual aggregate to: {output_path}")

if __name__ == "__main__":
    main()