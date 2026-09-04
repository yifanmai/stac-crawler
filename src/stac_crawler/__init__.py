import asyncio


from httpx import AsyncClient
from stac_crawler.crawl import crawl_root_stac_recursively

ROOT_CATALOG_URL = "https://storage.googleapis.com/cfo-public/catalog.json"





def hello() -> str:
    return "Hello from stac-crawler!"


async def main() -> None:
    response = await crawl_root_stac_recursively(ROOT_CATALOG_URL, "")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
