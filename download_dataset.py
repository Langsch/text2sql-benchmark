"""
Download BIRD Mini-Dev from Hugging Face and salva em data/bird/.

Saídas:
  data/bird/mini_dev_sqlite.json     → consumido pelo BirdLoader / benchmark
  data/bird/mini_dev_mysql.json      → idem, dialeto MySQL/MariaDB
  data/bird/mini_dev_postgresql.json → idem, dialeto PostgreSQL
  data/bird/mini_dev_sqlite.csv      → visualização no Data Wrangler (VS Code)

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
OUTPUT_DIR = Path("data/bird")

SPLITS = {
    "mini_dev_sqlite": ("mini_dev_sqlite.json", "sqlite"),
    "mini_dev_mysql": ("mini_dev_mysql.json", "mysql"),
    "mini_dev_pg": ("mini_dev_postgresql.json", "postgresql"),
}

FIELDS = ["db_id", "question", "evidence", "SQL", "difficulty"]


def _save_by_db(records: list[dict], dialect: str, base_dir: Path) -> int:
    by_db: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_db[r["db_id"]].append(r)

    for db_id, rows in by_db.items():
        folder = base_dir / "by_db" / db_id
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

    for split_name, (filename, dialect) in SPLITS.items():
        if split_name not in ds:
            print(f"  [aviso] split '{split_name}' não encontrado, pulando.")
            continue

        split = ds[split_name]
        out_json = OUTPUT_DIR / filename
        out_csv = OUTPUT_DIR / filename.replace(".json", ".csv")

        records = [
            {
                "db_id": row["db_id"],
                "question": row["question"],
                "evidence": row.get("evidence", ""),
                "SQL": row["SQL"],
                "difficulty": row.get("difficulty", "moderate"),
            }
            for row in split
        ]

        # combinado — usado pelo BirdLoader / benchmark
        out_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {out_json}  ({len(records)} instâncias)")

        split.to_csv(str(out_csv))
        print(f"  ✓ {out_csv}  (Data Wrangler combinado)")

        # separado por db_id
        n_dbs = _save_by_db(records, dialect, OUTPUT_DIR)
        print(f"  ✓ data/bird/by_db/*/{dialect}.*  ({n_dbs} bancos)")

    print("\nPronto!")
    print("  Arquivos combinados em:    data/bird/mini_dev_*.json/.csv")
    print("  Arquivos por banco em:     data/bird/by_db/<db_id>/<dialeto>.json/.csv")
    print()
    print("  Os arquivos SQLite (.sqlite) precisam ser baixados à parte")
    print("  pelo link oficial em bird-bench.github.io (Download BIRD Mini-Dev Complete Package).")
    print("  Coloque-os em:  data/bird/dev_databases/<db_id>/<db_id>.sqlite")


if __name__ == "__main__":
    main()
