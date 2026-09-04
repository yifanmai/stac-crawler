
from pathlib import Path
import json
import os
from typing import Dict

from httpx import URL
from urllib.parse import urljoin, urlsplit

from httpx import AsyncClient
from stac_crawler.models import Catalog, Collection, CatalogOrCollection, catalog_or_collection, Item

from urllib.parse import urljoin

class CrawlException(Exception):
    pass

def write_json(obj: Dict, file_path: str):
    # TODO: make this atomic
    actual_file_path = Path(file_path)
    actual_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(actual_file_path, "w") as out_file:
        # TODO: remove indent
        json.dump(obj, out_file, indent=2)


async def download_catalog(relative_path_from_base: str, source_base: str, target_base: str) -> CatalogOrCollection:
    source_path = urljoin(source_base, relative_path_from_base)
    target_path = os.path.join(target_base, relative_path_from_base)
    if os.path.isfile(target_path):
        print(f"skipping {source_path}")
        # TODO: Actually skip
    async with AsyncClient() as client:
        response = await client.get(urljoin(source_base, relative_path_from_base))
    catalog: CatalogOrCollection = catalog_or_collection.validate_python(response.json())
    rewrite_links(catalog, source_base)
    output_path = os.path.join(target_base, relative_path_from_base)
    write_json(catalog.model_dump(), output_path)
    return catalog



async def download_item(relative_path_from_base: str, source_base: str, target_base: str) -> Item:
    source_path = urljoin(source_base, relative_path_from_base)
    target_path = os.path.join(target_base, relative_path_from_base)
    if os.path.isfile(target_path):
        print(f"skipping {source_path}")
        # TODO: Actually skip
    async with AsyncClient() as client:
        response = await client.get(target_path)
    print(target_path)
    item: Item = Item.model_validate(response.json())
    # rewrite_links(catalog, source_base)
    output_path = os.path.join(target_base, relative_path_from_base)
    write_json(item.model_dump(), output_path)
    return item

async def crawl_catalog_recursively(relative_path_from_base: str, source_base: str, target_base: str) -> None:
    # print(relative_path_from_base)
    # print(source_base)
    # print(target_base)
    catalog = await download_catalog(relative_path_from_base, source_base, target_base)
    source_path = urljoin(source_base, relative_path_from_base)
    for link in catalog.links:
        if link.rel == "child":
            link_absolute_url = relative_to_absolute_url(link.href, source_path)
            link_relative_path_from_base = absolute_to_relative_url(link_absolute_url, source_base)
            print(link_relative_path_from_base)
            await crawl_catalog_recursively(link_relative_path_from_base, source_base, target_base)
    for link in catalog.links:
        if link.rel == "item":
            link_absolute_url = relative_to_absolute_url(link.href, source_path)
            link_relative_path_from_base = absolute_to_relative_url(link_absolute_url, source_base)
            print(link_relative_path_from_base)
            await download_item(link_relative_path_from_base, source_base, target_base)

def relative_to_absolute_url(url: str, base: str) -> str:
    """Convert an absolute URL to a relative URL
    
    Returns the URL unchanged if it is already relative"""
    original_url = URL(url)
    if original_url.is_absolute_url:
        return str(original_url)
    return urljoin(base, url)


def absolute_to_relative_url(url: str, base: str) -> str:
    """Convert an relative URL to a absolute URL
    
    Returns the URL unchanged if it is already relative"""
    original_url = URL(url)
    if original_url.is_relative_url:
        return str(original_url)
    if not url.startswith(base):
        raise CrawlException("absolute_to_relative_url only works if url is under base")
    return url.removeprefix(base)


def rewrite_links(catalog: CatalogOrCollection, root: str) -> None:
    """Given a catalog, update its links to make it a self-contained catalog.

    Only updates the current catalog; not recursive."""
    new_links = []
    for link in catalog.links:
        if link.rel == "self":
            continue
        elif link.rel == "child" or link.rel == "item":
            link.href = absolute_to_relative_url(link.href, root)
            new_links.append(link)
        elif link.rel == "root":
            # TODO: deal with this
            new_links.append(link)
        else:
            new_links.append(link)
    catalog.links = new_links
    

async def crawl_root_stac_recursively(source_catalog_path: str, target_base: str) -> None:
    if not source_catalog_path.endswith(".json"):
        raise CrawlException(f"Expected path '{source_catalog_path}' to end with .json")
    source_catalog_path_parts = source_catalog_path.split("/")
    if not source_catalog_path_parts:
        raise CrawlException(f"Malformed catalog path '{source_catalog_path}'")
    source_base = "/".join(source_catalog_path_parts[:-1]) + "/"
    await crawl_catalog_recursively(source_catalog_path_parts[-1], source_base, target_base)
