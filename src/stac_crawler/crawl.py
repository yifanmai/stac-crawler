from pathlib import Path
from typing import Dict, Union
from urllib.parse import urljoin
from urllib.parse import urlparse, urljoin
import asyncio
import json
import logging
import os
import posixpath

from httpx import AsyncClient, HTTPError, Response
from pydantic import BaseModel
from stac_crawler.models import Collection, CatalogOrCollection, Link, catalog_or_collection, Item, STACObject
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential, wait_random


logger = logging.getLogger(__name__)


REQUEST_WAIT_SECONDS = 0.2
"""How long to wait before requests"""


CRAWL_TARGET_REL = "crawl-target"
"""The rel type to use for the crawl-target link."""


CRAWL_TARGET_REL = "crawl-target"
"""The rel type to use for the crawl-target link."""


MAX_ITEM_LINKS = 5000
"""The maximium number of items permitted within a collection."""


MAX_CHILD_LINKS = 500
"""The maximium number of children permitted within a catalog."""


class CrawlException(Exception):
    pass


class TooManyLinksException(CrawlException):
    pass


STAC_INTERNAL_LINK_RELS = ["child", "item", "root", "parent", "collection"]


class CrawlCatalogStatistics(BaseModel):
    num_catalogs: int
    num_collections: int
    num_items: int

    def __add__(self, other: "CrawlCatalogStatistics") -> "CrawlCatalogStatistics":
        return CrawlCatalogStatistics(
            num_catalogs=self.num_catalogs + other.num_catalogs,
            num_collections=self.num_collections + other.num_collections,
            num_items=self.num_items + other.num_items,
        )

    def __radd__(self, other: "CrawlCatalogStatistics") -> None:
        self.num_catalogs += other.num_catalogs
        self.num_collections += other.num_collections
        self.num_items += other.num_items


def is_absolute_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme) and bool(parsed_url.netloc)


def write_json(stac_object: STACObject, file_path: str):
    # TODO: make this atomic
    actual_file_path = Path(file_path)
    actual_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(actual_file_path, "w") as out_file:
        out_file.write(stac_object.model_dump_json(exclude_unset=True))


def to_relative_url(target_url: str, base_url: str) -> str:
    """Return the target URL as a relative URL from the base URL"""
    # Parse URLs
    parsed_target_url = urlparse(target_url)
    base_dir_url = (
        base_url if base_url.endswith("/") else 
        "/".join(base_url.split("/")[:-1]) + "/"
    )
    parsed_base_url = urlparse(base_dir_url)

    # If target_url is already a relative URL, return it
    if not parsed_target_url.scheme or not parsed_target_url.netloc:
        return target_url

    # Check that both URLs are on the same host
    if parsed_target_url.scheme != parsed_base_url.scheme:
        raise ValueError(f"Target URL {target_url} and base URL {base_url} have different schemes")
    if parsed_target_url.netloc != parsed_base_url.netloc:
        raise ValueError(f"Target URL {target_url} and base URL {base_url} have different hosts")

    # Hack: Use posixpath to emulate URLs
    return posixpath.relpath(parsed_target_url.path, parsed_base_url.path)


def to_absolute_url(target_url: str, base_url: str) -> str:
    """Return target URL as an absolute URL, resolving it using the base URL if necessary"""
    # Parse URLs
    base_dir_url = (
        base_url if base_url.endswith("/") else 
        "/".join(base_url.split("/")[:-1]) + "/"
    )
    parsed_base_url = urlparse(base_dir_url)

    # If target_url is already an absolute URL, return it
    if is_absolute_url(target_url):
        return target_url

    # Check that base URL is absolute
    if not is_absolute_url(base_url):
        raise ValueError(f"Base URL {base_url} was not absolute")
    
    return urljoin(base_dir_url, target_url)


@retry(wait=wait_exponential(multiplier=5) + wait_random(0, 5), stop=stop_after_attempt(3), retry=retry_if_exception_type(HTTPError), reraise=True)
async def fetch_url_with_retries(url: str, client: AsyncClient) -> Response:
    response = await client.get(url)
    response.raise_for_status()
    return response


def get_destination_path(source_object_url: str, source_root_catalog_url: str, destination_root_catalog_path: str):
    source_object_relative_url = to_relative_url(source_object_url, source_root_catalog_url)
    destination_root_directory_path = os.path.split(destination_root_catalog_path)[0]
    return os.path.join(destination_root_directory_path, source_object_relative_url)
    

async def download_and_rewrite_catalog(source_catalog_url: str, source_root_catalog_url: str, destination_root_catalog_path: str) -> CatalogOrCollection:
    catalog: CatalogOrCollection
    if not is_absolute_url(source_catalog_url):
        raise ValueError(f"{source_catalog_url} was not an absolute URL")
    destination_path = get_destination_path(source_catalog_url, source_root_catalog_url, destination_root_catalog_path)
    if os.path.isfile(destination_path):
        logger.info(f"skipping {source_catalog_url}")
        with open(destination_path, "r") as destination_file:
            file_json = json.load(destination_file)
            return catalog_or_collection.validate_python(file_json)
    await asyncio.sleep(REQUEST_WAIT_SECONDS)
    async with AsyncClient() as client:
        logger.info(f"downloading {source_catalog_url}")
        response = await fetch_url_with_retries(urljoin(source_root_catalog_url, source_catalog_url), client)
    catalog = catalog_or_collection.validate_python(response.json())
    rewrite_links(catalog, source_catalog_url)
    add_crawl_target(catalog, source_catalog_url)
    write_json(catalog, destination_path)
    return catalog



async def download_and_rewrite_item(source_item_url: str, source_root_catalog_url: str, destination_root_catalog_path: str) -> Item:
    item: Item
    if not is_absolute_url(source_item_url):
        raise ValueError(f"{source_item_url} was not an absolute URL")
    destination_path = get_destination_path(source_item_url, source_root_catalog_url, destination_root_catalog_path)
    if os.path.isfile(destination_path):
        logger.debug(f"skipping {source_item_url}")
        with open(destination_path, "r") as destination_file:
            file_json = json.load(destination_file)
            return Item.model_validate(file_json)
    await asyncio.sleep(REQUEST_WAIT_SECONDS)
    async with AsyncClient() as client:
        logger.debug(f"downloading {source_item_url}")
        response = await fetch_url_with_retries(source_item_url, client)
    item = Item.model_validate(response.json())
    rewrite_links(item, source_item_url)
    add_crawl_target(item, source_item_url)
    write_json(item, destination_path)
    return item


async def crawl_catalog_recursively(source_catalog_url: str, source_root_catalog_url: str, destination_root_catalog_path: str) -> CrawlCatalogStatistics:
    catalog = await download_and_rewrite_catalog(source_catalog_url, source_root_catalog_url, destination_root_catalog_path)

    child_links = []
    item_links = []
    for link in catalog.links:
        if link.rel == "child":
            child_links.append(link)
        if link.rel == "item":
            item_links.append(link)

    if len(child_links) > MAX_CHILD_LINKS:
        raise TooManyLinksException(f"Catalog {source_catalog_url} has too many child links ({len(child_links)}); aborting.")
    if len(item_links) > MAX_ITEM_LINKS:
        raise TooManyLinksException(f"Catalog {source_catalog_url} has too many item links ({len(item_links)}); aborting.")

    statistics = CrawlCatalogStatistics(
        num_catalogs=1,
        num_collections=1 if isinstance(catalog, Collection) else 0,
        num_items=len(item_links),
    )

    for link in child_links:
        source_child_url = to_absolute_url(link.href, source_catalog_url)
        child_statistics = await crawl_catalog_recursively(source_child_url, source_root_catalog_url, destination_root_catalog_path)
        statistics += child_statistics
    for link in item_links:
        source_child_url = to_absolute_url(link.href, source_catalog_url)
        await download_and_rewrite_item(source_child_url, source_root_catalog_url, destination_root_catalog_path)
    return statistics


def rewrite_links(stac_object: STACObject, base_object_url: str) -> None:
    """Given a STAC object, mutate its links so that it can be in a self-contained catalog.

    Only updates the current STAC object; not recursive."""
    for link in stac_object.links:
        if link.rel == "self":
            continue
        elif link.rel in STAC_INTERNAL_LINK_RELS:
            link.href = to_relative_url(link.href, base_object_url)
        else:
            link.href = to_absolute_url(link.href, base_object_url)
    if isinstance(stac_object, Item) or (isinstance(stac_object, Collection) and stac_object.assets is not None):
        for asset in stac_object.assets.values():
            asset.href = to_absolute_url(asset.href, base_object_url)


def add_crawl_target(stac_object: STACObject, source_object_url: str) -> None:
    if not any(link.rel == CRAWL_TARGET_REL for link in stac_object.links):
        stac_object.links.append(Link(rel=CRAWL_TARGET_REL, href=source_object_url))


async def crawl_root_catalog_recursively(source_root_catalog_url: str, destination_root_catalog_path: str) -> CrawlCatalogStatistics:
    if not source_root_catalog_url.endswith(".json"):
        raise CrawlException(f"Expected source root catalog path '{source_root_catalog_url}' to end with .json")
    if not destination_root_catalog_path.endswith(".json"):
        raise CrawlException(f"Expected destination root catalog path '{destination_root_catalog_path}' to end with .json")
    return await crawl_catalog_recursively(source_root_catalog_url, source_root_catalog_url, destination_root_catalog_path)
