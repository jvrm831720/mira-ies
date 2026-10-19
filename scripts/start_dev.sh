#!/bin/bash
# Script de inicialização rápida do ambiente de desenvolvimento
# Uso: ./scripts/start_dev.sh

set -e

echo "🚀 Project Beacon — Iniciando ambiente de desenvolvimento..."

# Sobe a infraestrutura
echo "📦 Subindo PostgreSQL + Redis..."
docker compose up -d

echo "⏳ Aguardando banco ficar saudável..."
sleep 5

# Backend
echo "🐍 Preparando backend..."
cd backend

if [ ! -d ".venv" ]; then
    echo "Criando virtualenv..."
    python -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt --quiet

echo ""
echo "✅ Ambiente pronto!"
echo ""
echo "Para iniciar a API:"
echo "  cd backend"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Documentação: http://localhost:8000/docs"
echo "Health check:  http://localhost:8000/health"
