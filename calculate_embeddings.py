#!/usr/bin/env python3
"""Calculate vector embeddings for patent abstracts using a local model.

Queries the database for grants and publications that have an abstract
but no embedding, then uses a local SentenceTransformer model to compute
16-bit vector embeddings and store them as BLOBs in the database.

Idempotent: only processes records where abstract_embedding IS NULL.
Resumable: safe to interrupt and restart — already-computed embeddings
are skipped on the next run.
"""

import argparse
import logging
import sqlite3
import sys
import time

import numpy as np
from sentence_transformers import SentenceTransformer

# ============================================================
# Logging
# ============================================================

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s"


def setup_logging(level=logging.INFO):
    logging.basicConfig(format=LOG_FORMAT, level=level)


# ============================================================
# Embedding calculation
# ============================================================

ENCODE_CHUNK_SIZE = 50_000


def calculate_embeddings(
    db_path,
    model_path="nomic-embed-text-v1.5/",
    dataset="both",
    batch_size=64,
    limit=0,
    max_text_length=8000,
    device="cuda",
):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    cur = conn.cursor()

    datasets = ["publication", "grant"] if dataset == "both" else [dataset]

    logging.info("Loading model from %s", model_path)
    model_device = "cuda" if device == "multi-gpu" else device
    model = SentenceTransformer(model_path, trust_remote_code=True, device=model_device)
    dim = model.get_embedding_dimension()
    logging.info("Model loaded — embedding dimension: %d", dim)

    pool = None
    if device == "multi-gpu":
        pool = model.start_multi_process_pool()
        logging.info("Multi-GPU pool started")

    total_processed = 0

    try:
        for ds in datasets:
            logging.info("Processing %s abstracts", ds)

            count_sql = f"SELECT COUNT(*) FROM {ds} WHERE abstract_text IS NOT NULL AND abstract_text != '' AND abstract_embedding IS NULL"
            remaining = cur.execute(count_sql).fetchone()[0]
            logging.info("%s: %d records without embeddings", ds, remaining)

            if remaining == 0:
                continue

            select_sql = f"SELECT id, abstract_text FROM {ds} WHERE abstract_text IS NOT NULL AND abstract_text != '' AND abstract_embedding IS NULL"
            if limit > 0:
                select_sql += f" LIMIT {limit}"

            rows = cur.execute(select_sql).fetchall()
            logging.info("%s: processing %d records", ds, len(rows))

            start_time = time.time()
            ds_processed = 0

            for chunk_start in range(0, len(rows), ENCODE_CHUNK_SIZE):
                chunk = rows[chunk_start : chunk_start + ENCODE_CHUNK_SIZE]
                texts = [
                    t[:max_text_length] if len(t) > max_text_length else t
                    for _, t in chunk
                ]

                if device == "multi-gpu":
                    embeddings = model.encode(
                        texts,
                        pool=pool,
                        batch_size=batch_size,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
                else:
                    embeddings = model.encode(
                        texts,
                        batch_size=batch_size,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                        device=device,
                    )

                embeddings = embeddings.astype(np.float16)

                # Write back in DB-sized batches
                write_batch_size = 1000
                for i in range(0, len(chunk), write_batch_size):
                    sub_chunk = chunk[i : i + write_batch_size]
                    embs = embeddings[i : i + write_batch_size]
                    values = [
                        (emb.tobytes(), row_id)
                        for (row_id, _), emb in zip(sub_chunk, embs)
                    ]
                    cur.executemany(
                        f"UPDATE {ds} SET abstract_embedding = ? WHERE id = ?",
                        values,
                    )
                    conn.commit()

                ds_processed += len(chunk)
                total_processed += len(chunk)
                elapsed = time.time() - start_time
                rate = ds_processed / elapsed if elapsed > 0 else 0
                logging.info(
                    "%s: %d / %d done (%.0f/sec)", ds, ds_processed, len(rows), rate
                )

            logging.info("%s: complete — %d embeddings stored", ds, ds_processed)

    finally:
        if pool is not None:
            model.stop_multi_process_pool(pool)

    conn.close()
    logging.info("Total embeddings calculated: %d", total_processed)
    return total_processed


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Calculate vector embeddings for patent abstracts using a local model"
    )
    parser.add_argument(
        "--db",
        default="bibliographic_data.db",
        help="Path to SQLite database (default: %(default)s)",
    )
    parser.add_argument(
        "--dataset",
        choices=["publication", "grant", "both"],
        default="both",
        help="Which dataset to process (default: %(default)s)",
    )
    parser.add_argument(
        "--model",
        default="nomic-embed-text-v1.5/",
        help="Path to local SentenceTransformer model (default: %(default)s)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Abstracts per model forward pass (default: %(default)s)",
    )
    parser.add_argument(
        "--max-text-length",
        type=int,
        default=8000,
        help="Truncate abstracts longer than this many characters (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max records per dataset (0 = unlimited, default: %(default)s)",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cpu", "cuda", "multi-gpu"],
        help="Device for inference: cpu, single cuda, or multi-gpu (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: %(default)s)",
    )
    args = parser.parse_args()

    setup_logging(getattr(logging, args.log_level))

    calculate_embeddings(
        db_path=args.db,
        model_path=args.model,
        dataset=args.dataset,
        batch_size=args.batch_size,
        limit=args.limit,
        max_text_length=args.max_text_length,
        device=args.device,
    )


if __name__ == "__main__":
    main()
