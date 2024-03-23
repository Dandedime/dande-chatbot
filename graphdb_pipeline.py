from entity_resolution import EntityResolution
from neo4j_connection import Neo4jConnection
from data_structures import Entity, Relationship
from data_structures.key import TableDataKey

from typing import Optional, List
from dataclasses import asdict
import numpy as np
import pickle
import pandas as pd


class GraphDBPipeline:

    def __init__(self, entity_resolver: EntityResolution, snowflake_conn,
                 neo4j_conn: Neo4jConnection, test: bool=False):
        self.entity_resolver = entity_resolver
        self.snowflake_conn = snowflake_conn
        self.neo4j_conn = neo4j_conn
        self.test = test

    def upsert_entities(self, entities: List[Entity]):
        """
        Resolves entity and updates pinecone vetor store and graph db if necessary
        """
        ids = []
        scores = []
        matches = []
        for entity in entities:
            pinecone_id, matched_entity, score = self.entity_resolver.resolve(entity)
            entity.id = pinecone_id
            if matched_entity is None:
                if not self.test:
                    self.neo4j_conn.create_node(entity)
            else:
                query_dict = {f"query_{key}": value for key, value in
                              asdict(entity).items()}
                match_dict = {f"match_{key}": value for key, value in
                              matched_entity.items()}
                match_dict.update(query_dict)
                matches.append(match_dict)

            ids.append(pinecone_id)
            scores.append(score)
        return entities, scores, matches

    def upsert_relationship_edge(self, entity_node_ids, relationship_data: Relationship):
        pass

    def process_snowflake_table(self, table_name, data_key: TableDataKey,
                                row_limit: Optional[int] = None, query:
                                Optional[str] = None):
        cursor = self.snowflake_conn.cursor()
        if row_limit is None and query is None:
            query = f"select * from datadime1.public.{table_name}"
        elif query is None:
            query = f"select top {row_limit} * from datadime1.public.{table_name}"
        query_res = cursor.execute(query)
        scores_all = []
        ms_all = []
        for batch_res in query_res.fetch_pandas_batches():
            for _, row in batch_res.iterrows():
                entities, relationships, entity_relationship_idx = data_key.build(row)
                entities, scores, matches = self.upsert_entities(entities)
                scores_all += scores
                ms_all += matches

                if not self.test:
                    for relationship, entity_idxs in zip(relationships,
                                                         entity_relationship_idx):
                        self.neo4j_conn.create_edge(relationship,
                                                    entities[entity_idxs[0]],
                                                    entities[entity_idxs[1]])

        df = pd.DataFrame(ms_all)
        df.to_csv("matches.csv", index=False)
