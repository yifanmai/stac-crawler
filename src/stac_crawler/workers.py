import logging
import json
from collections import defaultdict
import os
from urllib.parse import urlsplit
from dataclasses import dataclass
import asyncio
from typing import Dict, List
from stac_crawler.crawl import crawl_root_stac_recursively



logger = logging.getLogger(__name__)

def get_catalog_host(catalog: dict) -> str: 
    catalog_url = catalog["url"]
    return urlsplit(catalog_url).netloc

def is_public_static_catalog(catalog: dict) -> bool:
    return not catalog["isPrivate"]  and not catalog["isApi"]

def get_queue_items(catalog_index_path: str):
    with open(catalog_index_path, "r") as in_file:
        all_catalogs = json.load(in_file)

    public_static_catalogs = [catalog for catalog in all_catalogs if is_public_static_catalog(catalog)]

    host_to_catalogs: Dict[str, List[dict]] = defaultdict(list)
    for catalog in public_static_catalogs:
        host_to_catalogs[get_catalog_host(catalog)].append(catalog)

    for host, catalogs in host_to_catalogs.items():
        yield CrawlQueueItem(host, 
                       [RootCatalogLink(
                           slug=catalog["slug"],
                           url=catalog["url"],
                       ) for catalog in catalogs])


@dataclass(frozen=True)
class RootCatalogLink:
    slug: str
    url: str


@dataclass(frozen=True)
class CrawlQueueItem:
    host: str
    root_catalog_links: List[RootCatalogLink]


async def process_crawl_queue_item(crawl_queue_item: CrawlQueueItem, output_path: str) -> None:
    for catalog_link in crawl_queue_item.root_catalog_links:
        await process_root_catalog_link(catalog_link, output_path)

async def process_root_catalog_link(root_catalog_link: RootCatalogLink, output_path: str) -> None:
    try:
        if not root_catalog_link.url.endswith(".json"):
            raise Exception(f"Root catalog URL {root_catalog_link} did not end with .json")
        root_catalog_file_name = root_catalog_link.url.split("/")[-1]
        destination_root_catalog_path = os.path.join(output_path, root_catalog_link.slug, root_catalog_file_name)
        await crawl_root_stac_recursively(root_catalog_link.url, destination_root_catalog_path)
    except Exception as e:
        logger.exception(e)


async def worker(queue: asyncio.Queue, output_path: str) -> None:
    while True:
        try:
            crawl_queue_item = queue.get_nowait()
            assert isinstance(crawl_queue_item, CrawlQueueItem)
            await process_crawl_queue_item(crawl_queue_item, output_path)
        except asyncio.QueueEmpty:
            return
        queue.task_done()


async def run_crawl_workers(catalog_index_path: str, output_path: str, num_workers: int):
    queue = asyncio.Queue()
    for queue_item in get_queue_items(catalog_index_path):
        queue.put_nowait(queue_item)

    worker_tasks = [
        asyncio.create_task(worker(queue, output_path))
         for _ in range(num_workers)
    ]
    results = await asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info(results)
