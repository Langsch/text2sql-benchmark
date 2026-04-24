#!/usr/bin/env bash
# Popula PostgreSQL e MariaDB com os dados do BIRD Mini-Dev.
# Uso: ./scripts/setup_databases.sh <caminho_para_mini_dev_data>

set -euo pipefail

BIRD_DATA_DIR="${1:-./data/bird}"

echo "==> Aguardando PostgreSQL..."
until pg_isready -h localhost -U bird; do sleep 2; done

echo "==> Carregando dados no PostgreSQL..."
# TODO: psql -U bird -d bird -f "$BIRD_DATA_DIR/BIRD_dev_postgres.sql"

echo "==> Aguardando MariaDB..."
until mariadb -h localhost -u bird -pbird -e "SELECT 1" &>/dev/null; do sleep 2; done

echo "==> Carregando dados no MariaDB..."
# TODO: mariadb -h localhost -u bird -pbird bird < "$BIRD_DATA_DIR/BIRD_dev_mysql.sql"

echo "==> Setup concluído."
