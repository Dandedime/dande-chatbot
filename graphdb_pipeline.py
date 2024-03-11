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
            matched_entity, pinecone_id, score = self.entity_resolver.resolve(entity)
            if matched_entity is None:
                # add node to graph db
                if not self.test:
                    self.upsert_entity_node(entity_data, pinecone_id)
            else:
                print("MATCHED:")
                print(entity)
                print(matched_entity)
                query_dict = {f"query_{key}": value for key, value in
                              asdict(entity).items()}
                match_dict = {f"match_{key}": value for key, value in
                              matched_entity.items()}
                match_dict.update(query_dict)
                matches.append(match_dict)

            ids.append(pinecone_id)
            scores.append(score)
        return ids, scores, matches

    def upsert_entity_node(self, entity_data, pinecone_id):
        pass

    def upsert_relationship_edge(self, entity_node_ids, relationship_data: Relationship):
        pass

    def process_snowflake_table(self, table_name, data_key: TableDataKey,
                                row_limit: Optional[int] = None, query:
                                Optional[str] = None):
        print('processing table')
        cursor = self.snowflake_conn.cursor()
        if row_limit is None and query is None:
            query = f"select * from datadime1.public.{table_name}"
        elif query is None:
            query = f"select top {row_limit} * from datadime1.public.{table_name}"
        print(query)
        query_res = cursor.execute(query)
        scores_all = []
        ms_all = []
        for batch_res in query_res.fetch_pandas_batches():
            for _, row in batch_res.iterrows():
                entities, relationships = data_key.build(row)
                print(entities)
                entity_ids, scores, matches = self.upsert_entities(entities)
                scores_all += scores
                ms_all += matches

                if not self.test:
                    self.batch_upsert_relationships(entity_ids, relationships)

        df = pd.DataFrame(ms_all)
        df.to_csv("matches.csv", index=False)
