import argparse
import logging
import asyncio
from pathlib import Path

from stac_crawler.workers import print_crawler_results_json, run_crawler_workers


CATALOGS_INDEX_PATH = "./data/catalogs.json"
STAC_CATALOGS_OUTPUT_PATH = "./output/stac_catalogs/"
LOGS_OUTPUT_PATH = "./output/logs/"
CATALOG_INDEX_PATH = "./data/catalogs.json"
DEFAULT_NUM_WORKERS = 8


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-index-path", help="Path to catalogs.json", default=CATALOGS_INDEX_PATH)
    parser.add_argument("--output-path", help="Path to root output directory", default=STAC_CATALOGS_OUTPUT_PATH)
    parser.add_argument("--logs-path", help="Path to root logs directory", default=LOGS_OUTPUT_PATH)
    parser.add_argument("--num-workers", help="Number of concurrent workers", type=int, default=DEFAULT_NUM_WORKERS)
    args = parser.parse_args()

    Path(args.output_path).mkdir(parents=True, exist_ok=True)
    Path(args.logs_path).mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(level=logging.WARNING)
    results = asyncio.run(run_crawler_workers(catalog_index_path=args.catalog_index_path, output_path=args.output_path, logs_path=args.logs_path, num_workers=args.num_workers))
    print_crawler_results_json(results)


if __name__ == "__main__":
    main()
