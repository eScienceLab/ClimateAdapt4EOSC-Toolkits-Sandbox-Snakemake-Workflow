import os
from dotenv import load_dotenv

# Load secrets from the .env file
load_dotenv()

# Load standard configuration file
configfile: "config/config.yaml"

# Inject the secrets into the config so scripts can access them uniformly
config["cds_url"] = os.getenv("CDSAPI_URL")
config["cds_key"] = os.getenv("CDSAPI_KEY")
