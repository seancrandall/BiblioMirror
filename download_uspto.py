#!/usr/bin/env python3
"""Download USPTO bibliographic bulk data from the Open Data Portal."""

import argparse
import json
import logging
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ============================================================
# Constants
# ============================================================

DATASET_PRODUCTS = {
    "publication": "APPBLXML",
    "grant": "PTBLXML",
}

BASE_URL = "https://api.uspto.gov/api/v1/datasets/products/{product}"

# ============================================================
# Logging
# ============================================================

LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s"


def setup_logging(logfile=None, level=logging.INFO):
    handlers = [logging.StreamHandler(sys.stdout)]
    if logfile:
        Path(logfile).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(logfile, mode="a"))
    logging.basicConfig(format=LOG_FORMAT, level=level, handlers=handlers)


# ============================================================
# Rate Limiter
# ============================================================

class RateLimiter:
    def __init__(self, rps=3.0):
        self.min_interval = 1.0 / max(rps, 0.001)
        self._last = 0.0

    def wait(self):
        now = time.time()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.time()


# ============================================================
# HTTP helpers
# ============================================================

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "uspto-biblio-mirror/1.0 (+local)"})


def request_with_retries(method, url, *, headers=None, max_retries=5, timeout=60):
    """Handle 429/5xx with backoff."""
    backoff = 1.5
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        resp = SESSION.request(method, url, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            sleep_for = float(ra) if ra and ra.isdigit() else delay
            logging.warning("429 Too Many Requests. Sleeping %.1fs (attempt %d/%d)", sleep_for, attempt, max_retries)
            time.sleep(sleep_for)
            delay *= backoff
            continue
        if 500 <= resp.status_code < 600:
            logging.warning("Server error %d. Sleeping %.1fs (attempt %d/%d)", resp.status_code, delay, attempt, max_retries)
            time.sleep(delay)
            delay *= backoff
            continue
        return resp
    return resp


# ============================================================
# API Key
# ============================================================

def resolve_api_key(args):
    """Resolve API key: env var → --api-key-file → error."""
    key = os.environ.get("ODP_API_KEY")
    if key:
        return key.strip()
    if args.api_key_file:
        try:
            with open(args.api_key_file, "r") as f:
                return f.read().strip()
        except Exception as e:
            logging.error("Cannot read API key from %s: %s", args.api_key_file, e)
            sys.exit(1)
    logging.error("No API key provided. Set ODP_API_KEY env var or use --api-key-file")
    sys.exit(1)


# ============================================================
# Date range partitioning
# ============================================================

def partition_date_range(start_date, end_date, batch_weeks=10):
    """Split a date range into batches of at most batch_weeks weeks."""
    batches = []
    current = start_date
    while current < end_date:
        batch_end = min(current + timedelta(weeks=batch_weeks), end_date)
        batches.append((current, batch_end))
        current = batch_end
    return batches


# ============================================================
# Download logic
# ============================================================

def query_dataset(product, start_date, end_date, api_key, rl):
    """Query the USPTO ODP API and return the JSON response."""
    url = BASE_URL.format(product=product)
    params = {
        "fileDataFromDate": start_date.strftime("%Y-%m-%d"),
        "fileDataToDate": end_date.strftime("%Y-%m-%d"),
        "includeFiles": "true",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }

    rl.wait()
    resp = request_with_retries("GET", url, headers=headers)
    if resp.status_code != 200:
        logging.error("API query failed: HTTP %d for %s (%s to %s)", resp.status_code, product, start_date, end_date)
        return None

    try:
        return resp.json()
    except json.JSONDecodeError as e:
        logging.error("Failed to parse API response: %s", e)
        return None


def extract_download_urls(api_response):
    """Extract download URLs from the API response.

    The ODP API returns:
    {
      "bulkDataProductBag": [{
        "productFileBag": {
          "fileDataBag": [{
            "fileName": "ipab20260122_wk04.zip",
            "fileDownloadURI": "https://...",
            "fileTypeText": "Data",
            ...
          }]
        }
      }]
    }
    """
    urls = []
    if not api_response:
        return urls

    # Navigate: bulkDataProductBag[].productFileBag.fileDataBag[]
    product_bag = api_response.get("bulkDataProductBag", [])
    if not product_bag:
        return urls

    for product in product_bag:
        file_bag = product.get("productFileBag", {})
        file_data_bag = file_bag.get("fileDataBag", [])
        for entry in file_data_bag:
            if isinstance(entry, dict):
                # Only include data files (not DTD/schema files)
                file_type = entry.get("fileTypeText", "")
                if file_type != "Data":
                    continue
                name = entry.get("fileName", "")
                url = entry.get("fileDownloadURI", "")
                if url and name:
                    urls.append((name, url))

    return urls


def download_zip(url, dest_path, api_key, rl):
    """Download a zip file from the given URL."""
    headers = {"x-api-key": api_key}
    rl.wait()
    resp = request_with_retries("GET", url, headers=headers, timeout=300)
    if resp.status_code != 200:
        logging.error("Download failed: HTTP %d for %s", resp.status_code, url[:80])
        return False

    content = resp.content
    # Check if it's actually a zip file
    if not content.startswith(b"PK"):
        # Might be a redirect response or error
        if len(content) < 1000:
            logging.error("Download did not return a zip file. Response: %s", content[:500])
        else:
            logging.error("Download did not return a zip file (got %d bytes starting with %s)",
                         len(content), content[:4])
        return False

    with open(dest_path, "wb") as f:
        f.write(content)

    return True


def extract_xml_from_zip(zip_path, output_dir):
    """Extract XML files from a zip into the output directory."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            xml_files = [n for n in z.namelist() if n.endswith(".xml")]
            for name in xml_files:
                z.extract(name, output_dir)
                logging.info("Extracted: %s", name)
            return xml_files
    except zipfile.BadZipFile as e:
        logging.error("Bad zip file %s: %s", zip_path, e)
        return []


def download_dataset(dataset, start_date, end_date, output_dir, api_key, rl,
                     batch_weeks=10, skip_existing=True):
    """Download all files for a dataset within a date range."""
    product = DATASET_PRODUCTS[dataset]
    download_dir = os.path.join(output_dir, "downloads", dataset)
    extract_dir = os.path.join(output_dir, "extracted", dataset)
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(extract_dir, exist_ok=True)

    batches = partition_date_range(start_date, end_date, batch_weeks)
    logging.info("Downloading %s: %s to %s in %d batches", dataset, start_date, end_date, len(batches))

    total_files = 0
    for i, (batch_start, batch_end) in enumerate(batches, 1):
        logging.info("Batch %d/%d: %s to %s", i, len(batches), batch_start, batch_end)

        api_response = query_dataset(product, batch_start, batch_end, api_key, rl)
        if not api_response:
            logging.warning("No response for batch %d, skipping", i)
            continue

        urls = extract_download_urls(api_response)
        if not urls:
            logging.warning("No download URLs found for batch %d", i)
            # Log the response structure for debugging
            logging.debug("API response keys: %s", list(api_response.keys()) if isinstance(api_response, dict) else "not a dict")
            continue

        logging.info("Found %d files in batch %d", len(urls), i)

        for name, url in urls:
            # Determine filename from URL or name
            if not name:
                name = url.split("/")[-1]
            # Ensure .zip extension
            if not name.endswith(".zip"):
                name += ".zip"

            zip_path = os.path.join(download_dir, name)

            if skip_existing and os.path.exists(zip_path):
                logging.info("Skipping existing: %s", name)
                # Still need to extract if not done
                xml_files = [n for n in zipfile.ZipFile(zip_path, "r").namelist() if n.endswith(".xml")]
                all_extracted = all(os.path.exists(os.path.join(extract_dir, x)) for x in xml_files)
                if not all_extracted:
                    extract_xml_from_zip(zip_path, extract_dir)
                continue

            if download_zip(url, zip_path, api_key, rl):
                logging.info("Downloaded: %s (%d bytes)", name, os.path.getsize(zip_path))
                extract_xml_from_zip(zip_path, extract_dir)
                total_files += 1
            else:
                logging.error("Failed to download: %s", name)

    logging.info("Download complete: %d new files for %s", total_files, dataset)
    return total_files


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Download USPTO bibliographic bulk data")
    parser.add_argument("--dataset", required=True, choices=["publication", "grant"],
                        help="Dataset to download")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default=".", help="Base output directory (default: current dir)")
    parser.add_argument("--api-key-file", help="File containing USPTO ODP API key")
    parser.add_argument("--batch-weeks", type=int, default=10, help="Weeks per download batch (default: 10)")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip already-downloaded files (default: True)")
    parser.add_argument("--rps", type=float, default=3.0, help="Max requests per second (default: 3.0)")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    setup_logging(level=getattr(logging, args.log_level.upper()))

    api_key = resolve_api_key(args)
    rl = RateLimiter(args.rps)

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    if start_date >= end_date:
        logging.error("Start date must be before end date")
        sys.exit(1)

    download_dataset(
        args.dataset, start_date, end_date,
        args.output_dir, api_key, rl,
        batch_weeks=args.batch_weeks,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    main()