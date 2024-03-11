from typing import List, Tuple, Optional, Union

from data_structures.classes import (
    Entity, Relationship, Corporation, Agency,
    Violation, Individual, Contribution, PAC
)

import json
import pandas as pd


class TableDataKey:
    def __init__(self, json_file):
        with open(json_file, 'r') as ifile:
            self.key_dict = json.load(ifile)

    def build(self, row: pd.Series) -> Tuple[List[Entity], List[Relationship]]:
        return self.build_entities(row), self.build_relationships(row)

    def _get_entity_type(self, entity_type: Union[dict, str], row):
        if isinstance(entity_type, str):
            return entity_type
        else:
            for entity_option in entity_type:
                if row[entity_option["column"]] == entity_option["value"]:
                    return entity_option["type"]

    def build_entities(self, row: pd.Series) -> List[Entity]:
        entities = []
        for entity_dict in self.key_dict["entities"]:
            entity_type = self._get_entity_type(entity_dict["entity_type"], row)
            if entity_type is None:
                print(row)
            fields_map = entity_dict["fields"][entity_type]
            vals = dict(zip(fields_map.keys(),
                            row[fields_map.values()].to_numpy()))
            vals["entity_type"] = entity_type
            if entity_type == "individual":
                entity = Individual(**vals)
            elif entity_type == "corporation":
                entity = Corporation(**vals)
            elif entity_type == "agency":
                entity = Agency(**vals)
            elif entity_type == "PAC":
                entity = PAC(**vals)
            entities.append(entity)
        return entities

    def build_relationships(self, row: pd.Series) -> List[Relationship]:
        relationships = []
        for relationship_dict in self.key_dict["relationships"]:
            relationship_type = relationship_dict["relationship_type"]
            fields_map = relationship_dict["fields"]
            vals = dict(zip(fields_map.keys(), row[fields_map.values()]))
            vals["relationship_type"] = relationship_type
            if relationship_type == "violation":
                relationship = Violation(**vals)
            elif relationship_type == "contribution":
                relationship = Contribution(**vals)
            relationships.append(relationship)
        return relationships

