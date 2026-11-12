# CORDEX Climate Data Processing Workflow

This repository contains a Snakemake workflow for downloading, cropping, merging, and aggregating CORDEX climate data.

## 🛠️ Setup & Installation

Follow these steps to set up your environment and install dependencies.

### 1. Clone the Repository & Navigate to Project Root
```bash
git clone <repository-url>
cd ClimateAdapt4EOSC-Toolkits-Sandbox-Snakemake-Workflow

```

### 2. Create and Activate a Virtual Environment

Create a dedicated virtual environment named **`cordex-snakemake-env`**:

* **macOS / Linux:**
```bash
python3 -m venv cordex-snakemake-env
source cordex-snakemake-env/bin/activate

```


* **Windows (PowerShell):**
```powershell
python -m venv cordex-snakemake-env
cordex-snakemake-env\Scripts\Activate.ps1

```



### 3. Install Dependencies from `pyproject.toml`

Upgrade pip and install the required workflow dependencies cleanly:

```bash
pip install --upgrade pip
pip install .

```

### 4. Configure Your Environment Secrets

Create a `.env` file in the project's root directory to securely manage your Copernicus Climate Data Store (CDS) credentials:

```env
CDSAPI_URL=[https://cds.climate.copernicus.eu/api](https://cds.climate.copernicus.eu/api)
CDSAPI_KEY=YOUR_USER_ID:YOUR_API_KEY

```

## Running the Workflow

1. **Execute the workflow** using multiple CPU cores:
```bash
snakemake --cores 6

```
