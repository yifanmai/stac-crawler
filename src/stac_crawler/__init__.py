import logging


import asyncio

from stac_crawler.workers import run_crawler_workers

STAC_CATALOGS_OUTPUT_PATH = "./output/stac_catalogs/"
CATALOG_INDEX_PATH = "./data/catalogs.json"

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(level=logging.WARNING)
    await run_crawler_workers(CATALOG_INDEX_PATH, STAC_CATALOGS_OUTPUT_PATH, num_workers=8)

if __name__ == "__main__":
    asyncio.run(main())
