# Valida o gateway Education Engine sem GitHub Actions.
# Pré-requisito: Python/venv do backend e PostgreSQL de testes local configurados.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m ruff check app/api/education_engine.py app/models/education_engine.py app/services/education_engine_client.py app/services/education_engine_secrets.py
if ($LASTEXITCODE -ne 0) { throw "Ruff falhou" }
python -m pytest -q tests/test_education_engine_bridge.py
if ($LASTEXITCODE -ne 0) { throw "Testes do motor acadêmico falharam" }
python -m alembic heads
if ($LASTEXITCODE -ne 0) { throw "Grafo Alembic inválido" }
Write-Host "Validação parcial local concluída: revise também o banco descartável e o conjunto completo." -ForegroundColor Green
