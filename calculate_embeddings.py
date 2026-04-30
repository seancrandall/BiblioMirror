#!/usr/bin/env python3
"""Calculate vector embeddings for patent abstracts using ollama.

Queries the database for grants and publications that have an abstract
but no embedding, then uses a local ollama embedding model to compute
vector embeddings and store them as BLOBs in the database.

Idempotent: only processes records where abstract_embedding IS NULL.
Resumable: safe to interrupt and restart — already-computed embeddings
are skipped on the next run.
"""

import argparse
import logging
import sqlite3
import struct
import sys
import time

import requests

# ============================================================
# Logging
# ============================================================

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s"


def setup_logging(level=logging.INFO):
    logging.basicConfig(format=LOG_FORMAT, level=level)


# ============================================================
# Ollama embedding client
# ============================================================

def get_embeddings(model, texts, base_url="http://localhost:11434", max_text_length=8000):
    """Call ollama /api/embed with a batch of texts. Returns list of float arrays.

    Texts longer than max_text_length are truncated to avoid 400 errors from
    models with limited context windows (e.g. nomic-embed-text: 8192 tokens).
    """
    truncated = [t[:max_text_length] if len(t) > max_text_length else t for t in texts]
    url = f"{base_url}/api/embed"
    payload = {"model": model, "input": truncated}
    r = requests.post(url, json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()
    return data["embeddings"]


# ============================================================
# Embedding calculation
# ============================================================

def calculate_embeddings(db_path, model="nomic-embed-text", base_url="http://localhost:11434",
                         dataset="both", batch_size=50, limit=0, max_text_length=8000):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    cur = conn.cursor()

    datasets = []
    if dataset == "both":
        datasets = ["publication", "grant"]
    else:
        datasets = [dataset]

    total_processed = 0

    for ds in datasets:
        logging.info("Processing %s abstracts with model %s", ds, model)

        # Count remaining
        count_sql = f"SELECT COUNT(*) FROM {ds} WHERE abstract_text IS NOT NULL AND abstract_text != '' AND abstract_embedding IS NULL"
        remaining = cur.execute(count_sql).fetchone()[0]
        logging.info("%s: %d records without embeddings", ds, remaining)

        if remaining == 0:
            continue

        # Fetch records needing embeddings
        select_sql = f"SELECT id, abstract_text FROM {ds} WHERE abstract_text IS NOT NULL AND abstract_text != '' AND abstract_embedding IS NULL"
        if limit > 0:
            select_sql += f" LIMIT {limit}"

        rows = cur.execute(select_sql).fetchall()
        logging.info("%s: processing %d records", ds, len(rows))

        start_time = time.time()
        ds_processed = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]

            try:
                embeddings = get_embeddings(model, texts, base_url, max_text_length)
            except requests.RequestException as e:
                logging.warning("Batch request failed (%s), retrying records individually", e)
                embeddings = None

            if embeddings is not None and len(embeddings) != len(batch):
                logging.warning("Embedding count mismatch: got %d, expected %d, retrying individually",
                                len(embeddings), len(batch))
                embeddings = None

            if embeddings is not None:
                dim = len(embeddings[0])
                for row_id, emb in zip(ids, embeddings):
                    blob = struct.pack(f"<{dim}f", *emb)
                    cur.execute(f"UPDATE {ds} SET abstract_embedding = ? WHERE id = ?", (blob, row_id))
            else:
                # Retry each record individually so one bad apple doesn't kill the batch
                for row_id, text in zip(ids, texts):
                    try:
                        single_emb = get_embeddings(model, [text], base_url, max_text_length)
                        dim = len(single_emb[0])
                        blob = struct.pack(f"<{dim}f", *single_emb[0])
                        cur.execute(f"UPDATE {ds} SET abstract_embedding = ? WHERE id = ?", (blob, row_id))
                    except requests.RequestException as e:
                        logging.error("Failed to embed %s id=%d: %s", ds, row_id, e)
                        # Mark as processed with empty embedding to skip on re-runs
                        cur.execute(f"UPDATE {ds} SET abstract_embedding = zeroblob(0) WHERE id = ?", (row_id,))

            conn.commit()
            ds_processed += len(batch)
            total_processed += len(batch)

            elapsed = time.time() - start_time
            rate = ds_processed / elapsed if elapsed > 0 else 0
            logging.info("%s: %d / %d done (%.0f/sec)", ds, ds_processed, len(rows), rate)

        conn.commit()
        logging.info("%s: complete — %d embeddings stored", ds, ds_processed)

    conn.close()
    logging.info("Total embeddings calculated: %d", total_processed)
    return total_processed


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Calculate vector embeddings for patent abstracts using ollama"
    )
    parser.add_argument("--db", default="bibliographic_data.db",
                        help="Path to SQLite database (default: %(default)s)")
    parser.add_argument("--dataset", choices=["publication", "grant", "both"],
                        default="both", help="Which dataset to process (default: %(default)s)")
    parser.add_argument("--model", default="nomic-embed-text",
                        help="Ollama embedding model (default: %(default)s)")
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                        help="Ollama base URL (default: %(default)s)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Abstracts per API call (default: %(default)s)")
    parser.add_argument("--max-text-length", type=int, default=8000,
                        help="Truncate abstracts longer than this many characters (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max records per dataset (0 = unlimited, default: %(default)s)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: %(default)s)")
    args = parser.parse_args()

    setup_logging(getattr(logging, args.log_level))

    calculate_embeddings(
        db_path=args.db,
        model=args.model,
        base_url=args.ollama_url,
        dataset=args.dataset,
        batch_size=args.batch_size,
        limit=args.limit,
        max_text_length=args.max_text_length,
    )


if __name__ == "__main__":
    main()