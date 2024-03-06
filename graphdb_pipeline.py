from entity_resolution import EntityResolution
from neo4j_connection import Neo4jConnection
from data_structures import Entity, Relationship
from data_structures.key import TableDataKey

from typing import Optional, List


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
        for entity in entities:
            matched_entity, pinecone_id = self.entity_resolver.resolve(entity)
            if matched_entity is None:
                # add node to graph db
                if not self.test:
                    self.upsert_entity_node(entity_data, pinecone_id)
            else:
                print("MATCHED:")
                print(entity)
                print(matched_entity)
            ids.append(pinecone_id)
        return ids

    def upsert_entity_node(self, entity_data, pinecone_id):
        pass

    def upsert_relationship_edge(self, entity_node_ids, relationship_data: Relationship):
        pass

    def process_snowflake_table(self, table_name, data_key: TableDataKey,
                                row_limit: Optional[int] = None):
        print('processing table')
        cursor = self.snowflake_conn.cursor()
        if row_limit is None:
            query = f"select * from datadime1.public.{table_name}"
        else:
            query = f"select top {row_limit} * from datadime1.public.{table_name}"
        query_res = cursor.execute(query)
        for batch_res in query_res.fetch_pandas_batches():
            for _, row in batch_res.iterrows():
                entities, relationships = data_key.build(row)
                print(entities)
                entity_ids = self.upsert_entities(entities)

                if not self.test:
                    self.batch_upsert_relationships(entity_ids, relationships)

