"""
Download BIRD Mini-Dev from Hugging Face e salva em data/bird/by_db/.

Estrutura gerada:
  data/bird/by_db/<db_id>/sqlite.json + sqlite.csv
  data/bird/by_db/<db_id>/mysql.json  + mysql.csv
  data/bird/by_db/<db_id>/postgresql.json + postgresql.csv

Uso:
  uv run python download_dataset.py
  # ou
  python download_dataset.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

DATASET_ID = "birdsql/bird_mini_dev"
OUTPUT_DIR = Path("data/bird/by_db")

SPLITS = {
    "mini_dev_sqlite": "sqlite",
    "mini_dev_mysql": "mysql",
    "mini_dev_pg": "postgresql",
}

FIELDS = ["db_id", "question", "evidence", "SQL", "difficulty"]


def _save_by_db(records: list[dict], dialect: str, base_dir: Path) -> int:
    by_db: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_db[r["db_id"]].append(r)

    for db_id, rows in by_db.items():
        folder = base_dir / db_id
        folder.mkdir(parents=True, exist_ok=True)

        (folder / f"{dialect}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with (folder / f"{dialect}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    return len(by_db)


def main() -> None:
    try:
        from datasets import load_dataset
    except ImportError:
        raise SystemExit(
            "Pacote 'datasets' não encontrado.\n"
            "Instale com:  uv pip install datasets\n"
            "ou:           pip install datasets"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Baixando '{DATASET_ID}' do Hugging Face...")
    ds = load_dataset(DATASET_ID)

    for split_name, dialect in SPLITS.items():
        if split_name not in ds:
            print(f"  [aviso] split '{split_name}' não encontrado, pulando.")
            continue

        records = [
            {
                "db_id": row["db_id"],
                "question": row["question"],
                "evidence": row.get("evidence", ""),
                "SQL": row["SQL"],
                "difficulty": row.get("difficulty", "moderate"),
            }
            for row in ds[split_name]
        ]

        n_dbs = _save_by_db(records, dialect, OUTPUT_DIR)
        print(f"  ✓ {dialect}  →  {n_dbs} bancos  ({len(records)} instâncias)")

    print(f"\nPronto! Arquivos em: {OUTPUT_DIR}/<db_id>/<dialeto>.json/.csv")
    print()
    print("  Os arquivos SQLite (.sqlite) precisam ser baixados à parte")
    print("  pelo link oficial em bird-bench.github.io (Download BIRD Mini-Dev Complete Package).")
    print("  Coloque-os em:  data/bird/dev_databases/<db_id>/<db_id>.sqlite")


if __name__ == "__main__":
    main()
