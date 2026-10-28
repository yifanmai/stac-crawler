# STAC Crawler

STAC Crawler is a tool that crawls a STAC catalog and saves a local mirror to local disk. 

## Usage

TODO

## Features

- Saves each file to disk as it is downloaded
- Resumes downloading a partially downloaded catalogs
- Limits the request rate to each host
- Retries failed requests using exponential backoff with jitter
- Parallelizes crawls of multiple hosts, but does not parallelize requests to a single host
- Preserves the relative file layout of the original catalog
- Preserves most raw field values of the original STAC objects
- Handles most STAC objects that would fail schema validation

## Limitations

STAC Crawler makes the following assumptions:

- The STAC root catalog URL ends with a `.json` extension.
- All child objects reside within the the directory tree of the STAC root catalog's parent directory.
- All STAC objects have a unique URL.
- The path of the URL of all STAC objects are valid filenames for the local filesystem.

## Design

STAC Crawler takes in the URL of target STAC root catalog and a local disk path. It performs a depth-first tree traversal of the STAC root catalog. At the start of visiting each STAC object, it processes the STAC object and saves the result to local disk. The local disk output path is based on the relative path between the STAC object's URL and the URL of the STAC root catalog's parent directory's URL.

When STAC objects are processed, href's in the STAC objects are modified as follows:

- Links to other STAC objects within the same catalog (i.e. with a `rel` value of "child", "item", "root", "parent", "collection") will be converted to relative URLs.
- Self-links (i.e. with a `rel` value of "self") are removed.
- All other links are converted to absolute URLs.
- Links to assets are converted to absolute URLs.

This ensures the resulting STAC catalog is internally valid and can be traversed, and that links to external URLs continue to function correctly. Additionally, the resulting catalog is guaranteed to be a [self-contained catalog](https://github.com/radiantearth/stac-api-spec/blob/release/v1.0.0/stac-spec/best-practices.md#self-contained-catalogs).

STAC Crawler invocation is idempotent, and an interrupted crawl will result in a valid STAC catalog subtree, except that some STAC objects will have broken child links because their child STAC objects were note downloaded yet. If a crawl is interrupted, STAC Crawler will resume by loading the already-downloaded STAC objects from local disk rather than the remote source, which avoids re-downloading the same STAC objects twice.

## Comparison with PySTAC

STAC Crawler is a custom crawler that was created for the [STAC Search](https://stacsearch.org/) project in order to create local mirrors of public static STAC catalogs listed on [STAC Index](https://stacindex.org/), which could then be indexed for searching. This required a crawler that scale to a large number of catalogs and files.

The official way to mirror a STAC catalog is to use PyStac's `Catalog.normalize_and_save()` ([documentation](https://pystac.readthedocs.io/en/latest/api/catalog.html), [tutorial](https://pystac.readthedocs.io/en/stable/tutorials/how-to-create-stac-catalogs.html)). In most cases, this is the best tool to use. However, it was not appropriate for STAC Search for the following reasons:

- PySTAC downloads the entire STAC catalog before saving it, and cannot resume from a partial download.
- PySTAC loads the entire STAC catalog into memory before saving it, which could cause problems for very large catalogs.
- PySTAC does not rate limit requests.
- PySTAC's `Catalog.normalize_and_save()` is slow because due to the time needed to modify  file paths of a large number of STAC objects. File path normalization requires modifying structural links, which requires scanning through lists of links in STAC objects to find the links to modify.
- PySTAC will raise an error if the source STAC objects fail schema validation.

Thus, STAC Crawler was written as a custom crawler to addresses these issues.
