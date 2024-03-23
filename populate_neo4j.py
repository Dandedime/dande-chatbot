from entity_resolution import EntityResolution
from neo4j_connection import Neo4jConnection
from data_structures import Entity, Relationship
from data_structures.key import TableDataKey
from langchain_community.vectorstores import Neo4jVector
from langchain_openai import OpenAIEmbeddings

from typing import Optional, List
from dataclasses import asdict
import numpy as np
import pickle
import pandas as pd
import streamlit as st
import neo4j


class GraphDBPipeline:

    def __init__(self, vector_db, snowflake_conn,
                 test: bool=False, max_retries=10):
        self.vector_db = vector_db
        self.snowflake_conn = snowflake_conn
        self.test = test
        self.max_retries = max_retries


    def process_snowflake_table(self, data_key: TableDataKey, query):
        cursor = self.snowflake_conn.cursor()
        query_res = cursor.execute(query)
        scores_all = []
        entity_strings_all = []
        for batch_res in query_res.fetch_pandas_batches():
            batch_entity_strs = []
            entities_metadata = []
            src_entity_idxs = []
            term_entity_idxs = []
            batch_relationships = []
            for _, row in batch_res.iterrows():
                entities, relationships, entity_relationship_idx = data_key.build(row)
                num_entities = len(batch_entity_strs)
                src_entity_idxs += [rel[0]+num_entities for rel
                                    in entity_relationship_idx]
                term_entity_idxs += [rel[1]+num_entities for rel
                                    in entity_relationship_idx]
                entity_strings = list(map(lambda x: x.to_text(), entities))
                batch_entity_strs += entity_strings
                entities_metadata += list(map(asdict, entities))
                batch_relationships += relationships
            print(f"UPSERTING {len(batch_entity_strs)}")
            passed = False
            counter = 0
            while not passed and counter < self.max_retries:
                try:
                    entity_ids = self.vector_db.add_texts(batch_entity_strs,
                                                          entities_metadata)
                    passed = True
                except neo4j.exceptions.SessionExpired:
                    counter += 1
            if counter >= self.max_retries:
                raise Exception("Reached maximum number of retries")

            self.add_relationships(batch_relationships, entity_ids,
                                   src_entity_idxs, term_entity_idxs)
            self.process_batch()
            #  relation_df = self._relationships_to_df(batch_relationships, entity_ids,
            #                                         src_entity_idxs,
            #                                          term_entity_idxs)
            #  relation_df.to_csv("tmp.csv", index=False)
            #  self.vector_db.query


    def _relationships_to_df(self, relationships, entity_ids, src_entity_idxs,
                             term_entity_idxs):
        src_ids = np.array(entity_ids)[src_entity_idxs]
        term_ids = np.array(entity_ids)[term_entity_idxs]
        df = pd.DataFrame([asdict(rel) for rel in relationships])
        df["source"] = src_ids
        df["terminal"] = term_ids
        return df

    def add_relationships(self, relationships, entity_ids, src_entity_idxs,
                          term_entity_idxs, relationship_type="contribution"):
        df = self._relationships_to_df(relationships, entity_ids,
                                       src_entity_idxs, term_entity_idxs)

        query = "UNWIND $data AS row "\
            "MATCH (src:Individual {entity_id: row.source}) "\
            "MATCH (targ:Individual {entity_id: row.terminal}) "\
            f"CREATE (src)-[rel:{relationship_type}]->(targ) "
        #  df.to_csv("import/tmp.csv", index=False)
        #  query = """CALL apoc.load.csv("tmp.csv") YIELD map as row
        #  MATCH (src:Individual {id: row.source})
        #  MATCH (targ:Individual {id: row.terminal})
        #  CREATE (src)-[rel:Temp]->(targ)"""
        query += "\nSET "+", ".join([f"rel.{column}=row.{column}" for
                                           column in df.columns[:-2]])
        print(query)
        params = {"data": df.to_dict("records")}
        res = self.vector_db.query(query, params=params)
        print(res)

    def process_batch(self):
        with self.vector_db._driver.session(database=self.vector_db._database) as session:
            session.execute_write(self.add_identity_edges)
            session.execute_write(self.collapse_clusters)

    @staticmethod
    def add_identity_edges(tx, max_num_matches=10, threshold=0.98):
        query = "MATCH (n:Individual) "\
        f"""CALL db.index.vector.queryNodes("vector", {max_num_matches}, n.embedding) YIELD node as 
        similar_node, score\n"""\
        f"where n<>similar_node and score > {threshold}\n"\
        "CREATE (n)-[:Identity {score: score}]->(similar_node)"
        tx.run(query)

    @staticmethod
    def collapse_clusters(tx, threshold=0.999):
        merge_query = """MATCH (n:Individual)
        WITH collect(n) AS nodes
        UNWIND nodes AS node
        CALL {
          WITH node
          MATCH (node)-[rel:Identity]->(connected)\n"""\
          f"WHERE rel.score > {threshold}\n"\
          """WITH collect(connected) AS connectedNodes, node
          CALL apoc.refactor.mergeNodes(connectedNodes + node) YIELD node AS mergedNode
          RETURN mergedNode
        }
        RETURN mergedNode"""
        print("MERGING")
        tx.run(merge_query)

        clear_self_rels = """MATCH (a:Individual) -[rel:Identity]-(a)
        DELETE rel"""

        print("REMOVING SELF ID")
        tx.run(clear_self_rels)

        consolidate_identities = """MATCH
        (a:Individual)-[rels:Identity]->(b:Individual)
        WHERE a <> b
        WITH a, b, rels
        ORDER BY rels.score DESC
        WITH a, b, collect(rels) AS sortedRels
        WITH a, b, sortedRels[0] AS topRelationship, sortedRels[1..] AS
        restOfRelationships
        FOREACH (rel IN restOfRelationships |
        DELETE rel
        )
        RETURN a, b, topRelationship"""

        print("CONSOLIDATING")
        tx.run(consolidate_identities)




if __name__ == "__main__":
    embedding = OpenAIEmbeddings(api_key=st.secrets.OPENAI_API_KEY)
    vector_db = Neo4jVector.from_existing_graph(embedding=embedding,
                            username=st.secrets.neo4j.user,
                            password=st.secrets.neo4j.pwd,
                            url=st.secrets.neo4j.uri,
                            node_label="Individual",
                            embedding_node_property="embedding",
                            text_node_properties = ["text"],
                            pre_delete_collection=True

                        )
    pipeline = GraphDBPipeline(vector_db, st.connection("snowflake"))
    table_key = TableDataKey(f"table_keys/az.json")
    #  query = """select top 5000 concat(trim(L_NAME_OR_ORG), ', ', trim(F_NAME)) as
    #  contributor_name, address, city, state, zip, occupation,
    #  concat(CAN_LAST_NAME, ', ', CAN_FIRST_NAME) as recipient_name,
    #  received_date, amount from statedata.public.mi_demo where L_NAME_OR_ORG ilike 'DEVOS%' and
    #  can_first_name is not null and F_NAME is not null and L_NAME_OR_ORG is not
    #  null;"""
    query = """select top 5000 t.amount, t.transactiondate, case when
    n.firstname is null then n.lastname else trim(concat(n.lastname, ' ',
    IFNULL(n.suffix, ''), ', ', n.firstname, ' ',
    IFNULL(n.middlename, '')))
    end as contributor_name, n.lastname as contributor_lname, trim(n.firstname) as
    contributor_fname, n.middlename as contributor_mname, n.suffix as
    contributor_suffix, n.address1 as contributor_address1, n.address2 as
    contributor_address2, n.city as contributor_city, n.state as
    contributor_state, n.zipcode as contributor_zipcode, n.occupation as
    contributor_occupation, n.employer as contributor_employer, case when
    n.firstname is null and n.middlename is null and n.lastname ilike '%pac%' then 'pac' when
    n.firstname is null and n.middlename is null then 'org' else 'individual' end as contributor_type,
    case when n2.firstname is null then n2.lastname else
    trim(concat(n2.lastname, ' ', IFNULL(n2.suffix, ''), ', ',
    n2.firstname, ' ',
    IFNULL(n2.middlename, ''))) end as recipient_name, n2.lastname as
    recipient_lname, trim(n2.firstname) as recipient_fname, n2.middlename as
    recipient_mname, n2.suffix as recipient_suffix, n2.address1 as
    recipient_address1, n2.address2 as recipient_address2, n2.city as
    recipient_city, n2.state as recipient_state, n2.zipcode as
    recipient_zipcode, n2.occupation as recipient_occupation, n2.employer as
    recipient_employer, case when n2.firstname is null and n2.middlename is
    null and n2.lastname ilike
    '%pac%' then 'pac' when n2.firstname is null and n2.middlename is null then 'org' else 'individual'
    end as recipient_type from statedata.public.az_transactions t join
    statedata.public.az_names n on
    t.nameid=n.nameid join statedata.public.az_committees com on com.committeeid=t.committeeid
    join statedata.public.az_names n2 on com.candidatenameid=n2.nameid where com.candidatenameid
    is not null;"""
    pipeline.process_snowflake_table(table_key, query)
