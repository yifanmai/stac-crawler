import logging
import json
from collections import defaultdict
import os
import traceback
from urllib.parse import urlsplit
from dataclasses import dataclass
import asyncio
from typing import Dict, List, Optional, Union

from pydantic import BaseModel

from stac_crawler.crawl import CrawlCatalogStatistics, crawl_root_catalog_recursively


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


class CrawlCatalogError(BaseModel):
    exception_summary: str
    exception: Optional[str]

CrawlCatalogResult = Union[CrawlCatalogStatistics, CrawlCatalogError]



class CrawlWorkersResult(BaseModel):
    successes: Dict[str, CrawlCatalogStatistics]
    failures: Dict[str, CrawlCatalogError]


def exception_to_crawl_catalog_error(exception: BaseException) -> CrawlCatalogError:
    return CrawlCatalogError(exception_summary="\n".join(traceback.format_exception_only(exception)).strip(), exception="\n".join(traceback.format_exception(exception)))

async def process_crawl_queue_item(crawl_queue_item: CrawlQueueItem, output_path: str, logs_path: str) -> Dict[str, CrawlCatalogResult]:
    results: Dict[str, CrawlCatalogResult] = {}
    for catalog_link in crawl_queue_item.root_catalog_links:
        try:
            crawl_catalog_result = await process_root_catalog_link(catalog_link, output_path, logs_path)
            results[catalog_link.slug] = crawl_catalog_result
        except Exception as e:
            results[catalog_link.slug] = exception_to_crawl_catalog_error(e)
    return results


async def process_root_catalog_link(root_catalog_link: RootCatalogLink, output_path: str, logs_path: str) -> CrawlCatalogResult:
    if not root_catalog_link.url.endswith(".json"):
        raise Exception(f"Root catalog URL {root_catalog_link} did not end with .json")
    root_catalog_file_name = root_catalog_link.url.split("/")[-1]
    destination_root_catalog_path = os.path.join(output_path, root_catalog_link.slug, root_catalog_file_name)
    log_file_path = os.path.join(logs_path, f"{root_catalog_link.slug}.log")
    return await crawl_root_catalog_recursively(root_catalog_link.url, destination_root_catalog_path, log_file_path)


async def worker(queue: asyncio.Queue, output_path: str, logs_path: str) -> None:
    results: Dict[str, CrawlCatalogResult] = {}
    while True:
        try:
            crawl_queue_item = queue.get_nowait()
            assert isinstance(crawl_queue_item, CrawlQueueItem)
            crawl_queue_item_results = await process_crawl_queue_item(crawl_queue_item, output_path, logs_path)
            results.update(crawl_queue_item_results)
        except asyncio.QueueEmpty:
            return results
        queue.task_done()


async def run_crawler_workers(catalog_index_path: str, output_path: str, logs_path: str, num_workers: int) -> CrawlWorkersResult:
    queue = asyncio.Queue()
    for queue_item in get_queue_items(catalog_index_path):
        queue.put_nowait(queue_item)

    worker_tasks = [
        asyncio.create_task(worker(queue, output_path, logs_path))
         for _ in range(num_workers)
    ]
    worker_results = await asyncio.gather(*worker_tasks, return_exceptions=True)
    results = CrawlWorkersResult(successes={}, failures={})
    for worker_index, worker_result in enumerate(worker_results):
        if isinstance(worker_result, BaseException):
            results.failures[f"_worker_error_{worker_index}"] = exception_to_crawl_catalog_error(worker_result)
        elif isinstance(worker_result, dict):
            for url, result in worker_result.items():
                if isinstance(result, CrawlCatalogStatistics):
                    results.successes[url] = result
                elif isinstance(result, CrawlCatalogError):
                    results.failures[url] = result
                else:
                    raise Exception(f"Unexpected result type {type(result)}")
        else:
            raise Exception(f"Unexpected worker result type {type(worker_result)}")
    return results


def print_crawler_results(results: CrawlWorkersResult) -> None:
    print("Errors:")
    for key, result in results.failures.items():
        print(f"{key}: {result.exception_summary}")
    print()
    print("Statistics:")
    for key, result in results.successes.items():
        print(f"{key}: {result.model_dump()}")



def print_crawler_results_json(results: CrawlWorkersResult) -> None:
    print(results.model_dump_json(indent=2))
