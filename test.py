from graphdb_pipeline import GraphDBPipeline
from entity_resolution import EntityResolution
from data_structures.key import TableDataKey
from neo4j_connection import Neo4jConnection

import pinecone
import streamlit as st



def get_pc_index(index_name, clear=True):
    pc = pinecone.Pinecone(api_key = st.secrets.PINECONE_API_KEY)
    if index_name in pc.list_indexes().names():
        pc.delete_index(index_name)
    pc.create_index(
        name=index_name,
         dimension=1536,
         metric='cosine',
         spec=pinecone.ServerlessSpec(
                      cloud='aws',
                      region='us-west-2'
        )
    )
    index = pc.Index(index_name)
    return index


def test(index_name="entities2", table_name="corporate_regulatory_violations",
         sample_size=500):
    table_key = TableDataKey(f"table_keys/{table_name}.json")
    index = get_pc_index(index_name)
    print(index)

    er = EntityResolution(index)

    db_conn = st.connection("snowflake")
    neo4j_conn = Neo4jConnection(uri=st.secrets.neo4j.uri,
                                user=st.secrets.neo4j.user,
                                pwd=st.secrets.neo4j.pwd)
    pipeline = GraphDBPipeline(er, db_conn, neo4j_conn, test=True)
    pipeline.process_snowflake_table(table_name, table_key,
                                     row_limit=sample_size)


if __name__ == "__main__":
    test()
