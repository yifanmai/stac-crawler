import argparse
import logging
import asyncio
import os
from pathlib import Path

from stac_crawler.crawl import crawl_root_catalog_recursively


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("root_catalog_url", help="URL of to input STAC root catalog", type=str)
    parser.add_argument("output_directory_path", help="Path to output root directory", type=str)
    args = parser.parse_args()
    root_catalog_url = args.root_catalog_url
    output_directory_path = args.output_directory_path
    Path(output_directory_path).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(level=logging.WARNING)
    root_catalog_file_name = root_catalog_url.split("/")[-1]
    destination_root_catalog_path = os.path.join(output_directory_path, root_catalog_file_name)
    result = asyncio.run(crawl_root_catalog_recursively(root_catalog_url, destination_root_catalog_path))
    
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
