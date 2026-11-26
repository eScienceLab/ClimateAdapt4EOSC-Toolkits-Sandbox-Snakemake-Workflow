import os
from dotenv import load_dotenv

# Load secrets from the .env file
load_dotenv()

# Load standard configuration file
configfile: "config/config.yaml"

# Inject the secrets into the config so scripts can access them uniformly
config["cds_url"] = os.getenv("CDSAPI_URL")
config["cds_key"] = os.getenv("CDSAPI_KEY")

# Include modular rule files
include: "rules/download_crop.smk"

# Define the top-level target rule
def get_all_outputs(wildcards):
    outputs = []
    start_year = config["start_year"]
    end_year = config["end_year"]

    for scenario in config["selected_scenarios"]:
        for var in config["cds_variables"]:
            agg_type = "sum" if var == "mean_precipitation_flux" else "mean"
            # Target the final merged historical + scenario file
            outputs.append(f"output_final_merged/{scenario}/annual_{agg_type}_{var}-{start_year}-{end_year}_{scenario}.nc")
    return outputs

rule all:
    input:
        get_all_outputs