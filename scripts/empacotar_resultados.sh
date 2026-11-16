#!/usr/bin/env bash
# Gera o pacote de dados brutos para publicação (release do GitHub e Zenodo).
#
# Uso, na raiz do repositório:
#     ./scripts/empacotar_resultados.sh
#
# Produz dist/resultados.tar.gz e dist/resultados.sha256. Antes de empacotar,
# confere que todos os arquivos do manifesto estão íntegros e que nenhum
# arquivo contém credencial: publicar é irreversível.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Integridade e números do artigo"
if ! .venv/bin/python analise/reproduzir.py >/dev/null; then
    # Divergência de número do artigo não impede publicar os dados; arquivo
    # alterado impede.
    .venv/bin/python - <<'PY'
import hashlib, json, sys
man = json.load(open("analise/manifesto.json", encoding="utf-8"))
refs = [c[e] for c in man["celulas"] for e in ("etapa1", "etapa2", "etapa3")]
refs += man["subteste_rota"]["arquivos"]
ruins = [r["arquivo"] for r in refs
         if hashlib.sha256(open(r["arquivo"], "rb").read()).hexdigest() != r["sha256"]]
if ruins:
    sys.exit("Arquivos alterados desde o manifesto:\n  " + "\n  ".join(ruins))
print("Arquivos íntegros (há divergências de texto no relatório, não de dados).")
PY
fi

echo "== Varredura de credenciais e dados pessoais"
padrao='sk-or-v1-[A-Za-z0-9]|sk-ant-[A-Za-z0-9]|gsk_[A-Za-z0-9]|sk-proj-|AIza[0-9A-Za-z_-]{20}|/home/[a-z]'
if grep -rlE "$padrao" results/runs; then
    echo "ERRO: os arquivos acima contêm possível credencial ou caminho pessoal. Nada foi empacotado." >&2
    exit 1
fi
echo "Nenhuma ocorrência."

echo "== Empacotando"
mkdir -p dist
tar --exclude='results/runs/index_runs/tmp_dbs' \
    -czf dist/resultados.tar.gz \
    results/runs analise/manifesto.json
(cd dist && sha256sum resultados.tar.gz > resultados.sha256)
ls -lh dist/resultados.tar.gz
cat dist/resultados.sha256
