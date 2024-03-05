from dataclasses import dataclass, field
from typing import Optional

@dataclass(kw_only=True)
class Entity:
    name: str
    entity_type: Optional[str] = field(default=None, init=False)

    def to_text(self):
        data_str = f"{entity_data.entity_type} named {entity_data.name} with "

        field_strs = [f"{field} of {value}" for field, value in
                      asdict(entity_data).items() if field not in
                      ["entity_type", "name"]]
        data_str += ", ".join(field_strs)
        return data_str

@dataclass(kw_only=True)
class Individual(Entity):
    entity_type = "individual"
    title: Optional[str] = None
    address: str
    city: str
    state: str
    zipcode: str
    gender: str
    job_title: Optional[str] = None


@dataclass
class Corporation(Entity):
    entity_type = "corporation"
    major_industry: str
    specific_industry: str
    ownership_structure: str
    hq_state: str

#  @dataclass
#  class PAC(Entity):



@dataclass
class Relationship:
    relationship_type: str

@dataclass
class Contribution(Relationship):
    amount: float
    date: str


@dataclass
class MarriedTo(Relationship):
    pass

