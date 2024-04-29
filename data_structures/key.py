from typing import List, Tuple, Optional, Union

from data_structures.classes import (
    Entity, Relationship, Corporation, Agency,
    Violation, Individual, Contribution, PAC, Organization
)

import json
import pandas as pd


class TableDataKey:
    def __init__(self, json_file):
        """Class to handle the extraction of entities and relationships from a
        snowflake table
        Args:
            json_file: Path to the json file corresponding to table in question
                that contains instructinos for entity and relationship mapping
        """
        with open(json_file, 'r') as ifile:
            self.key_dict = json.load(ifile)
        self.table_name = self.key_dict["table_name"]
        self.query = self._load_query()
        self.relationship_type = self.key_dict["relationship_type"]
        entity_types = []
        for entity in self.key_dict["entities"]:
            for entity_type in entity["entity_type"]:
                entity_types.append(entity_type["type"])
        self.entity_types = set(entity_types)

    def _load_query(self):
        query = self.key_dict.get("query")
        query_file = self.key_dict.get("query_file")
        if query is None and query_file is not None:
            with open(query_file, "r") as ifile:
                query = ifile.read()
        return query

    def build(self, row: pd.Series, row_index: Optional[int] = None) -> Tuple[List[Entity], List[Relationship]]:
        """Extract any entity and relationships from the given row"""
        entities = self.build_entities(row, row_index)
        relationships, entity_mapping = self.build_relationships(row, row_index)
        return entities, relationships, entity_mapping

    def _get_entity_type(self, entity_type: Union[dict, str], row):
        if isinstance(entity_type, str):
            return entity_type
        else:
            for entity_option in entity_type:
                if row[entity_option["column"]] == entity_option["value"]:
                    return entity_option["type"]

    def build_entities(self, row: pd.Series, row_index: Optional[int] = None) -> List[Entity]:
        """Extract entities from the given row"""
        entities = []
        for entity_dict in self.key_dict["entities"]:
            entity_type = self._get_entity_type(entity_dict["entity_type"], row)
            if entity_type is None:
                print(row)
            fields_map = entity_dict["fields"][entity_type]
            vals = dict(zip(fields_map.keys(),
                            list(map(lambda x: x.lower() if isinstance(x, str)
                                     else x,
                                 row[fields_map.values()].to_numpy()))))
            vals["entity_type"] = entity_type
            if row_index is not None:
                vals["row_index"] = row_index
            if entity_type == "individual":
                entity = Individual(**vals)
            elif entity_type == "organization":
                entity = Organization(**vals)
            elif entity_type == "corporation":
                entity = Corporation(**vals)
            elif entity_type == "agency":
                entity = Agency(**vals)
            elif entity_type == "pac":
                entity = PAC(**vals)
            entities.append(entity)
        return entities

    def build_relationships(self, row: pd.Series, row_index: Optional[int] =
                            None) -> List[Relationship]:
        """Extract relationships from the given row"""
        relationships = []
        entity_mapping = []
        for relationship_dict in self.key_dict["relationships"]:
            relationship_type = relationship_dict["relationship_type"]
            fields_map = relationship_dict["fields"]
            vals = dict(zip(fields_map.keys(), row[fields_map.values()]))
            vals["relationship_type"] = relationship_type
            if row_index is not None:
                vals["row_index"] = row_index
            if relationship_type == "violation":
                relationship = Violation(**vals)
            elif relationship_type == "contribution":
                relationship = Contribution(**vals)
            relationships.append(relationship)
            entity_mapping.append((relationship_dict["source_entity"],
                                   relationship_dict["terminal_entity"]))
        return relationships, entity_mapping

