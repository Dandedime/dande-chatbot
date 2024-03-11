from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(kw_only=True)
@dataclass
class Entity:
    name: str
    entity_type: Optional[str] = field(default=None, init=False)

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
    entity_type = "individual"
    title: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    gender: Optional[str] = None
    job_title: Optional[str] = None


@dataclass
class Corporation(Entity):
    entity_type = "corporation"
    parent_company: Optional[str] = None
    industry: Optional[str] = None
    ownership_structure: Optional[str] = None
    hq_state: Optional[str] = None

@dataclass
class Agency(Entity):
    entity_type = "agency"


@dataclass
class PAC(Entity):
    state: Optional[str] = None

@dataclass
class Relationship:
    relationship_type: str

@dataclass
class Contribution(Relationship):
    amount: float
    date: str
    cycle: Optional[int] = None

@dataclass
class Violation(Relationship):
    amount: float
    year: int
    violation_type: str


@dataclass
class MarriedTo(Relationship):
    pass


