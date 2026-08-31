#!/usr/bin/env bash
# Sobe PostgreSQL e MariaDB e carrega os dumps do BIRD Mini-Dev.
#
# O BIRD distribui os bancos prontos para MySQL e PostgreSQL — nao ha migracao
# a fazer a partir do SQLite. Baixe o "BIRD Mini-Dev Complete Package" em
# bird-bench.github.io e aponte este script para a pasta descompactada.
#
# Uso:
#   ./scripts/setup_databases.sh /caminho/para/minidev
#
# Espera encontrar, sob esse caminho:
#   MINIDEV_postgresql/BIRD_dev.sql   (ou */postgresql/*.sql)
#   MINIDEV_mysql/BIRD_dev.sql        (ou */mysql/*.sql)

set -euo pipefail

MINIDEV_DIR="${1:-}"
if [[ -z "$MINIDEV_DIR" ]]; then
  echo "erro: informe o caminho do pacote Mini-Dev descompactado." >&2
  echo "uso: $0 /caminho/para/minidev" >&2
  exit 1
fi
if [[ ! -d "$MINIDEV_DIR" ]]; then
  echo "erro: diretorio nao encontrado: $MINIDEV_DIR" >&2
  exit 1
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

# Credenciais vindas do .env, com os mesmos padroes do docker-compose.yml.
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi
PG_USER="${POSTGRES_USER:-bird}"
PG_DB="${POSTGRES_DB:-bird}"
MDB_USER="${MARIADB_USER:-bird}"
MDB_PASS="${MARIADB_PASSWORD:-bird}"
MDB_DB="${MARIADB_DB:-bird}"

encontrar_dump() {
  # $1 = padrao de pasta (postgres|mysql)
  #
  # O pacote Mini-Dev traz cinco .sql: tres arquivos "*_gold.sql" com as
  # queries gabarito (~100 KB) e dois "BIRD_dev.sql" com schema e dados
  # (~1 GB). Escolher pelo MAIOR evita carregar o arquivo de queries por
  # engano — que foi o que aconteceu quando a selecao era alfabetica.
  find "$MINIDEV_DIR" -ipath "*$1*" -name "*.sql" -size +100M 2>/dev/null |
    xargs -r ls -S 2>/dev/null | head -1
}

echo "==> Subindo os containers"
docker compose up -d

echo "==> Aguardando PostgreSQL"
until docker compose exec -T postgresql pg_isready -U "$PG_USER" >/dev/null 2>&1; do
  sleep 2
done
echo "    pronto"

DUMP_PG="$(encontrar_dump postgres || true)"
if [[ -z "$DUMP_PG" ]]; then
  echo "    [aviso] nenhum dump PostgreSQL encontrado em $MINIDEV_DIR — pulando"
else
  echo "==> Carregando PostgreSQL a partir de $DUMP_PG"
  docker compose exec -T postgresql psql -U "$PG_USER" -d "$PG_DB" < "$DUMP_PG"
fi

echo "==> Aguardando MariaDB"
until docker compose exec -T mariadb \
      mariadb -u "$MDB_USER" -p"$MDB_PASS" -e "SELECT 1" >/dev/null 2>&1; do
  sleep 2
done
echo "    pronto"

DUMP_MDB="$(encontrar_dump mysql || true)"
if [[ -z "$DUMP_MDB" ]]; then
  echo "    [aviso] nenhum dump MySQL encontrado em $MINIDEV_DIR — pulando"
else
  echo "==> Carregando MariaDB a partir de $DUMP_MDB"
  docker compose exec -T mariadb \
    mariadb -u "$MDB_USER" -p"$MDB_PASS" "$MDB_DB" < "$DUMP_MDB"
fi

echo
echo "==> Conferindo o que foi carregado"
echo "--- PostgreSQL: schemas encontrados"
docker compose exec -T postgresql psql -U "$PG_USER" -d "$PG_DB" -tAc \
  "SELECT schema_name FROM information_schema.schemata
   WHERE schema_name NOT IN ('pg_catalog','information_schema','public')
     AND schema_name NOT LIKE 'pg_%' ORDER BY 1" || true
echo "--- MariaDB: databases encontrados"
docker compose exec -T mariadb mariadb -u "$MDB_USER" -p"$MDB_PASS" -N -e \
  "SELECT schema_name FROM information_schema.schemata
   WHERE schema_name NOT IN
     ('information_schema','mysql','performance_schema','sys') ORDER BY 1" || true

echo
echo "==> Setup concluido."
echo "    Confira acima se os 11 db_id do BIRD aparecem. Se o PostgreSQL"
echo "    listar schemas e o MariaDB listar databases com os nomes dos bancos"
echo "    (california_schools, card_games, ...), os conectores ja funcionam."
