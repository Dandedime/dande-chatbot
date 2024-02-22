

class GraphDBPipeline:

    def __init__(self, entity_resolver: EntityResolution, snowflake_conn,
                 neo4j_conn):
        self.entity_resolver = entity_resolver
        self.snowflake_conn = snowflake_conn
        self.neo4j_conn = neo4j_conn

    def upsert_entity(self, entity_data: EntityData):
        """
        Resolves entity and updates pinecone vetor store and graph db if necessary
        """
        matched, pinecone_id = self.entity_resolver.resolve(entity_data)
        if not matched:
            # add node to graph db
            self.upsert_entity_node(entity_data, pinecone_id)
        return pinecone_id

    def upsert_entity_node(self, entity_data, pinecone_id):
        pass

    def upsert_relationship_edge(self, entity_node_ids, relationship_data: RelationshipData):
        pass

    def process_snowflake_table(self, table_name, entity_data_key,
                                relationship_data_key):
        # query (with a batch size?) table, create entity and relationship data
        # class instances, then call upsert
        query_res = self.db_conn.batch_query(f"select * from {table_name}",
                                             batch_size=self.query_batch_size)
        for batch_res in query_res:
            # NOTE: entities needs to be (num_rows, 2)
            entities = build_entities(batch_res, entity_data_key)
            relationships = build_relationships(batch_res,
                                                relationship_data_key)
            entity_ids = self.batch_upsert_entities(entities)

            # add nodes (if ids arent in graphdb already) and relations to
            # neo4j
            self.batch_upsert_relationships(entity_ids, relationships)

