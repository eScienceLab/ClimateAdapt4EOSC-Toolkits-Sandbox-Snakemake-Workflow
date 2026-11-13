rule download_crop:
    output:
        out_nc = "{out_dir}/{scenario}/{variable}_{year_start}_{year_end}_CROPPED.nc"
    params:
        work_dir = lambda wc: config["scenarios"][wc.scenario]["work_dir"]
    script:
        "../scripts/download_and_crop.py"

rule merge_cropped_to_final:
    input:
        cropped_nc = "{out_dir}/{scenario}/{variable}_{year_start}_{year_end}_CROPPED.nc"
    output:
        final_nc = "{out_dir}/{scenario}/{variable}-{year_start}-{year_end}.nc"
    wildcard_constraints:
        variable = "((?!annual_)[a-z0-9_]+)"  # Prevents matching annual prefixed names
    script:
        "../scripts/merge_cropped_files.py"

rule annual_aggregate:
    input:
        nc_file = "{out_dir}/{scenario}/{variable}-{year_start}-{year_end}.nc"
    output:
        annual_nc = "{out_dir}/{scenario}/annual_{agg_type}_{variable}-{year_start}-{year_end}.nc"
    wildcard_constraints:
        variable = "[a-z0-9_]+",
        agg_type = "sum|mean",
        year_start = "\\d{4}",
        year_end = "\\d{4}"  # Prevents year_end from eating scenario suffixes like _rcp_4.5
    script:
        "../scripts/annual_aggregate.py"

rule merge_historical_and_scenarios:
    input:
        annual_nc = "output_cropped_{scenario}/{scenario}/annual_{agg_type}_{variable}-{year_start}-{year_end}.nc"
    output:
        final_nc = "output_final_merged/{scenario}/annual_{agg_type}_{variable}-{year_start}-{year_end}_{scenario}.nc"
    wildcard_constraints:
        agg_type = "sum|mean",
        variable = "[a-z0-9_]+",
        year_start = "\\d{4}",
        year_end = "\\d{4}"
    params:
        scenario_dir = lambda wc: f"output_cropped_{wc.scenario}",
        hist_dir = "output_cropped"
    script:
        "../scripts/merge_historical_and_scenarios.py"