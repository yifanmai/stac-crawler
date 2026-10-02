import logging
import asyncio
import json
import os
from pathlib import Path
import posixpath
from typing import Dict
from urllib.parse import urlparse, urljoin

from urllib.parse import urljoin

from httpx import AsyncClient
from stac_crawler.models import CatalogOrCollection, catalog_or_collection, Item, STACObject


logger = logging.getLogger(__name__)


REQUEST_WAIT_SECONDS = 0.2
"""How long to wait before requests"""


class CrawlException(Exception):
    pass



def is_absolute_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme) and bool(parsed_url.netloc)


def write_json(obj: Dict, file_path: str):
    # TODO: make this atomic
    actual_file_path = Path(file_path)
    actual_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(actual_file_path, "w") as out_file:
        json.dump(obj, out_file)


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
        response = await client.get(urljoin(source_root_catalog_url, source_catalog_url))
    catalog = catalog_or_collection.validate_python(response.json())
    rewrite_links(catalog, source_catalog_url)
    write_json(catalog.model_dump(), destination_path)
    return catalog



async def download_and_rewrite_item(source_item_url: str, source_root_catalog_url: str, destination_root_catalog_path: str) -> Item:
    item: Item
    if not is_absolute_url(source_item_url):
        raise ValueError(f"{source_item_url} was not an absolute URL")
    destination_path = get_destination_path(source_item_url, source_root_catalog_url, destination_root_catalog_path)
    if os.path.isfile(destination_path):
        # logger.info(f"skipping {source_item_url}")
        with open(destination_path, "r") as destination_file:
            file_json = json.load(destination_file)
            return Item.model_validate(file_json)
    await asyncio.sleep(REQUEST_WAIT_SECONDS)
    async with AsyncClient() as client:
        # logger.info(f"downloading {source_item_url}")
        response = await client.get(source_item_url)
    item = Item.model_validate(response.json())
    rewrite_links(item, source_item_url)
    # TODO: rewrite links
    write_json(item.model_dump(), destination_path)
    return item


async def crawl_catalog_recursively(source_catalog_url: str, source_root_catalog_url: str, destination_root_catalog_path: str) -> None:
    catalog = await download_and_rewrite_catalog(source_catalog_url, source_root_catalog_url, destination_root_catalog_path)
    for link in catalog.links:
        if link.rel == "child":
            source_child_url = to_absolute_url(link.href, source_catalog_url)
            await crawl_catalog_recursively(source_child_url, source_root_catalog_url, destination_root_catalog_path)
    for link in catalog.links:
        if link.rel == "item":
            source_child_url = to_absolute_url(link.href, source_catalog_url)
            # link_absolute_url = relative_to_absolute_url(link.href, source_path)
            # link_relative_path_from_base = absolute_to_relative_url(link_absolute_url, source_base)
            # print(link_relative_path_from_base)
            await download_and_rewrite_item(source_child_url, source_root_catalog_url, destination_root_catalog_path)


STAC_INTERNAL_LINK_RELS = ["child", "item", "root", "parent", "collection"]


def rewrite_links(catalog: STACObject, base_object_url: str) -> None:
    """Given a catalog, update its links to make it a self-contained catalog.

    Only updates the current catalog; not recursive."""
    new_links = []
    for link in catalog.links:
        if link.rel == "self":
            continue
        elif link.rel in STAC_INTERNAL_LINK_RELS:
            link.href = to_relative_url(link.href, base_object_url)
            new_links.append(link)
        else:
            link.href = to_absolute_url(link.href, base_object_url)
            new_links.append(link)
    catalog.links = new_links
    

async def crawl_root_stac_recursively(source_root_catalog_url: str, destination_root_catalog_path: str) -> None:
    if not source_root_catalog_url.endswith(".json"):
        raise CrawlException(f"Expected source root catalog path '{source_root_catalog_url}' to end with .json")
    if not destination_root_catalog_path.endswith(".json"):
        raise CrawlException(f"Expected destination root catalog path '{destination_root_catalog_path}' to end with .json")
    await crawl_catalog_recursively(source_root_catalog_url, source_root_catalog_url, destination_root_catalog_path)

