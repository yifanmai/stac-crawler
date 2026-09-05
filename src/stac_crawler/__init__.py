

import asyncio

from httpx import AsyncClient
from stac_crawler.crawl import crawl_root_stac_recursively
from stac_crawler.workers import crawl_catalogs_in_index

ROOT_CATALOG_URL = "https://storage.googleapis.com/cfo-public/catalog.json"


async def main() -> None:
    # await crawl_catalogs_in_index(num_workers=4)
    response = await crawl_root_stac_recursively(ROOT_CATALOG_URL, "/home/yifanmai/oss/stac-crawler/output/cfo-public/catalog.json")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
