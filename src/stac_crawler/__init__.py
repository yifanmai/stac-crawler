

import asyncio

from httpx import AsyncClient
from stac_crawler.crawl import crawl_root_stac_recursively

ROOT_CATALOG_URL = "https://storage.googleapis.com/cfo-public/catalog.json"






async def main() -> None:
    response = await crawl_root_stac_recursively(ROOT_CATALOG_URL, "/home/yifanmai/oss/stac-crawler/output/cfo-public/catalog.json")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
