from __future__ import annotations

import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
import os


BASE_DIR = Path(__file__).resolve().parents[1]
SQLITE_PATH = BASE_DIR / "data" / "structurebase.db"
load_dotenv(BASE_DIR / ".env")


def main() -> None:
    mongodb_uri = os.environ.get("STRUCTUREBASE_MONGODB_URI", "").strip()
    mongodb_db_name = os.environ.get("STRUCTUREBASE_MONGODB_DB_NAME", "structurebase").strip()
    mongodb_collection = os.environ.get("STRUCTUREBASE_MONGODB_COLLECTION", "listings").strip()

    if not mongodb_uri:
        raise SystemExit("Set STRUCTUREBASE_MONGODB_URI before running this migration.")

    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row
    rows = sqlite.execute("SELECT * FROM listings ORDER BY id ASC").fetchall()

    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
    collection = client[mongodb_db_name][mongodb_collection]
    collection.create_index("public_id", unique=True)

    migrated = 0
    for row in rows:
        document = dict(row)
        document["public_id"] = f"legacy-{row['id']}"
        document["source_sqlite_id"] = row["id"]
        collection.update_one(
            {"public_id": document["public_id"]},
            {"$set": document},
            upsert=True,
        )
        migrated += 1

    print(f"Migrated {migrated} listings from {SQLITE_PATH} to MongoDB.")


if __name__ == "__main__":
    main()
