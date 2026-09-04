from typing import Annotated, List, Literal, Union

from pydantic import BaseModel, Field, ConfigDict, TypeAdapter

class Link(BaseModel):
    rel: str
    href: str
    model_config = ConfigDict(extra='allow')

class Catalog(BaseModel):
    type: Literal["Catalog"] = "Catalog"
    stac_version: str
    id: str
    description: str
    links: List[Link]
    model_config = ConfigDict(extra='allow')

class Collection(BaseModel):
    type: Literal["Collection"] = "Collection"
    stac_version: str
    id: str
    description: str
    links: List[Link]
    model_config = ConfigDict(extra='allow')


class Item(BaseModel):
    type: Literal["Feature"] = "Feature"
    links: List[Link]
    model_config = ConfigDict(extra='allow')

CatalogOrCollection = Annotated[Union[Catalog, Collection], Field(discriminator='type')]
catalog_or_collection = TypeAdapter(CatalogOrCollection)

STACObject = Union[Item, CatalogOrCollection]
