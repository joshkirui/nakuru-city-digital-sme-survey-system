# Launch the dashboard against the demo database.
# Usage:  .\run_demo.ps1
$env:MSME_DB = Join-Path $PSScriptRoot "data\demo.db"
if (-not (Test-Path $env:MSME_DB)) {
    python (Join-Path $PSScriptRoot "seed_demo.py")
}
python (Join-Path $PSScriptRoot "app.py")
