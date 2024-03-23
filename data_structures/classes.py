from functools import cached_property
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List

from data_structures.utils import get_name_parts


@dataclass(kw_only=True)
@dataclass
class Entity:
    name: str
    entity_type: Optional[str] = field(default=None, init=False)
    id: Optional[str] = None

    def to_text(self):
        data_str = f"{self.entity_type} named {self.name}"

        dict_rep = asdict(self)
        if len(dict_rep):
            data_str += " with "
            field_strs = [f"{field} of {value}" for field, value in
                          asdict(self).items() if field not in
                          ["entity_type", "name"] and value is not None]
            data_str += ", ".join(field_strs)
        return data_str

@dataclass(kw_only=True)
class Individual(Entity):
    entity_type = "Individual"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    title: Optional[str] = None
    suffix: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    employer: Optional[str] = None

    def __post_init__(self):
        if self.first_name is None:
            self.first_name = self.name_parts["first"]
        if self.last_name is None:
            self.last_name = self.name_parts["last"]
        if self.middle_name is None:
            self.middle_name = self.name_parts.get("middle")
        if self.title is None:
            self.title = self.name_parts["title"]
        if self.suffix is None:
            self.suffix = self.name_parts["suffix"]

    @cached_property
    def name_parts(self) -> Dict[str, str]:
        return get_name_parts(self.name)


@dataclass
class Corporation(Entity):
    entity_type = "Corporation"
    parent_company: Optional[str] = None
    industry: Optional[str] = None
    ownership_structure: Optional[str] = None
    hq_state: Optional[str] = None

@dataclass
class Agency(Entity):
    entity_type = "Agency"


@dataclass
class Organization(Entity):
    entity_type = "Organization"
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None

@dataclass
class PAC(Entity):
    entity_type = "PAC"
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None

@dataclass
class Relationship:
    relationship_type: str

@dataclass
class EntityMatch(Relationship):
    relationship_type: str = "EntityMatch"
    similarity: Optional[float] = None

@dataclass
class Contribution(Relationship):
    relationship_type: str = "Contribution"
    amount: Optional[float] = None
    date: Optional[str] = None
    cycle: Optional[int] = None

@dataclass
class Violation(Relationship):
    relationship_type: str = "Violation"
    amount: Optional[float] = None
    year: Optional[int] = None
    violation_type: Optional[str] = None


@dataclass
class MarriedTo(Relationship):
    pass


def from_data_dict(entity_dict) -> Entity:
    if entity_dict["entity_type"] == "individual":
        return Individual(**entity_dict)
    elif entity_dict["entity_type"] == "corporation":
        return Corporation(**entity_dict)
    elif entity_dict["entity_type"] == "agency":
        return Agency(**entity_dict)
    else:
        raise Exception("Entity type does not exist")