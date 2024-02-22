from dataclasses import dataclass

@dataclass
class Entity:
    name: str
    entity_type: str

@dataclass
class Individual(Entity):
    title: str
    address: str
    city: str
    state: str
    zipcode: str
    gender: str
    job_title: str

@dataclass
class Corporation(Entity):
    major_industry: str
    specific_industry: str
    ownership_structure: str
    hq_state: str

#  @dataclass
#  class PAC(Entity):



@dataclass
class Relationship:
    relationship_type: str

@datalcass
class Contribution(Relationship):
    amount: float
    date: str


@dataclass
class MarriedTo(Relationship):
    pass

