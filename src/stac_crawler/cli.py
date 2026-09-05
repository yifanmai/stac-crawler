import argparse
import logging


import asyncio

from stac_crawler.workers import run_crawl_workers

STAC_CATALOGS_OUTPUT_PATH = "./output/stac_catalogs/"
CATALOG_INDEX_PATH = "./data/catalogs.json"
DEFAULT_NUM_WORKERS = 8

def crawl_all_catalogs() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-index-path", help="Path to catalogs.json", default=CATALOG_INDEX_PATH)
    parser.add_argument("--output-path", help="Path to root output directory", default=STAC_CATALOGS_OUTPUT_PATH)
    parser.add_argument("--num-workers", help="Number of concurrent workers", type=int, default=DEFAULT_NUM_WORKERS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(level=logging.WARNING)
    asyncio.run(run_crawl_workers(args.catalog_index_path, args.output_path, args.num_workers))

if __name__ == "__main__":
    crawl_all_catalogs()
