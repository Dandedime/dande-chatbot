from entity_resolution import EntityResolution
from neo4j_connection import Neo4jConnection
from data_structures import Entity, Relationship
from data_structures.key import TableDataKey
from langchain_community.vectorstores import Neo4jVector
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings

from embedding import EntityEmbedder

from typing import Optional, List
from dataclasses import asdict
import numpy as np
import pickle
import pandas as pd
import streamlit as st
import neo4j
import time
import argparse


class GraphDBPipeline:

    def __init__(self, vector_db: Neo4jVector, snowflake_conn,
                 test: bool=False, max_retries: int = 8):
        """Class to handle populating graph db from a snowflake table including
        basic entity recognition
        Args:
            vector_db: Neo4jVector instance connecting to target graph db
            snowflake_conn: Snowflake connection to pull table form
            max_retries: Max number of retries upon SessionExpired erros
        """
        self.vector_db = vector_db
        self.snowflake_conn = snowflake_conn
        self.test = test
        self.max_retries = max_retries
        self.neo4j_url = st.secrets.neo4j.uri
        self.username = "neo4j"
        self.pwd = st.secrets.neo4j.pwd


    def _get_min_id(self) -> int:
        maxid = self.vector_db.query("MATCH (n) RETURN MAX(ID(n)) as max;")[0]["max"] or -1
        return maxid+1

    def process_snowflake_table(self, data_key: TableDataKey,
                                csv_file: Optional[str] = None, row_index: int
                                = 0, max_batch_size=500,
                                relationship_type="contribution"):
        """
        Args:
            data_key: TableDataKey instance with instructions for extracting
                entities and relationships from the query results or provided csv
                file
            query: Snowflake query whose results are to be upserted into graph
                db. Either query or csv_file must be provided
            csv_file: csv file path containing data to be upserted into graph
                db. Either csv_file or query must be provided
            row_index: Row index to start the upsert at. Allows upserts that
                crashed to be continued. Only works if using csv_file!
            max_batch_size: Max size of each dataframe to be processed
        """
        if csv_file is not None:
            query_res = pd.read_csv(csv_file).replace({np.nan: None})
            query_res = [query_res.iloc[row_index:]]
        else:
            cursor = self.snowflake_conn.cursor()
            query = data_key.query
            if query is None:
                query = f"select * from {data_key.table_name}"
            query_res = cursor.execute(query).fetch_pandas_batches()

        scores_all = []
        entity_strings_all = []
        for batch_res in query_res:
            min_id = self._get_min_id()

            # Split batch_res into dataframes no bigger than max_batch_size
            num_batches = np.ceil(batch_res.shape[0] / float(max_batch_size)).astype(np.int32)
            for df in np.array_split(batch_res, num_batches):
                batch_entity_strs = []
                entities_metadata = []
                src_entity_idxs = []
                term_entity_idxs = []
                batch_relationships = []
                min_idx = df.index[0]
                for idx, row in df.iterrows():
                    entities, relationships, entity_relationship_idx = \
                        data_key.build(row, idx)
                    num_entities = len(batch_entity_strs)
                    src_entity_idxs += [rel[0]+num_entities for rel
                                        in entity_relationship_idx]
                    term_entity_idxs += [rel[1]+num_entities for rel
                                        in entity_relationship_idx]
                    entity_strings = list(map(lambda x: x.to_text(), entities))
                    batch_entity_strs += entity_strings
                    entities_metadata += list(map(asdict, entities))
                    batch_relationships += relationships

                passed = False
                counter = 0
                while not passed and counter < self.max_retries:
                    try:
                        entity_ids = self.vector_db.add_texts(batch_entity_strs,
                                                              entities_metadata)
                        passed = True
                    except neo4j.exceptions.SessionExpired:
                        time.sleep(4)
                        self._reset_neo4j_conn()
                        counter += 1
                if counter >= self.max_retries:
                    raise Exception("Reached maximum number of retries")

                self.add_relationships(batch_relationships, entity_ids,
                                       src_entity_idxs, term_entity_idxs,
                                       relationship_type=relationship_type)
                self.process_batch(min_idx, data_key)

        with self.vector_db._driver.session(database=self.vector_db._database) as session:
            session.execute_write(self.assign_neighbor_score)
        self.vector_db._driver.close()


    def _reset_neo4j_conn(self):
        self.vector_db._driver = neo4j.GraphDatabase.driver(self.neo4j_url,
                                                            auth=(self.username,
                                                             self.pwd))

    def _relationships_to_df(self, relationships: List[Relationship],
                             entity_ids: List[str], src_entity_idxs: List[int],
                             term_entity_idxs: List[int]) -> pd.DataFrame:
        src_ids = np.array(entity_ids)[src_entity_idxs]
        term_ids = np.array(entity_ids)[term_entity_idxs]
        df = pd.DataFrame([asdict(rel) for rel in relationships])
        df["source"] = src_ids
        df["terminal"] = term_ids
        return df


    def add_relationships(self, relationships: List[Relationship], entity_ids:
                          List[str], src_entity_idxs: List[int],
                          term_entity_idxs: List[int], relationship_type: str = "Contribution"):
        df = self._relationships_to_df(relationships, entity_ids,
                                       src_entity_idxs, term_entity_idxs)

        query = "UNWIND $data AS row "\
            "MATCH (src {entity_id: row.source}) "\
            "MATCH (targ {entity_id: row.terminal}) "\
            f"CREATE (src)-[rel:{relationship_type}]->(targ) "
        query += "\nSET "+", ".join([f"rel.{column}=row.{column}" for
                                           column in df.columns[:-2]])

        self.vector_db.query(query, params={"data": df.to_dict("records")})


    def process_batch(self, min_id: int, data_key):
        with self.vector_db._driver.session(database=self.vector_db._database) as session:
            session.execute_write(self.add_identity_edges,
                                  data_key.entity_types, min_id)

        self.collapse_clusters(min_id)
        with self.vector_db._driver.session(database=self.vector_db._database) as session:
            session.execute_write(self.clean_up, min_id)

    @staticmethod
    def add_identity_edges(tx, entity_types, min_id: int, max_num_matches: int = 5,
                           threshold: int = 0.96):
        for entity_type in entity_types:
            query = f"MATCH (n {{entity_type: '{entity_type}'}})\nWHERE n.row_index >= {min_id}\n"\
            f"""CALL db.index.vector.queryNodes("vector", {max_num_matches}, n.embedding) YIELD node as 
            similar_node, score\n"""\
            f"where n.entity_type = similar_node.entity_type and n<>similar_node and score > {threshold}\n"\
            """and  (n.suffix = similar_node.suffix  OR (n.suffix is null or
            similar_node.suffix is null))\n"""\
            """and  (n.gender = similar_node.gender  OR (n.gender is null or
            similar_node.gender is null))\n"""\
                """CREATE (n)-[rel:Identity {score: score}]->(similar_node)
                SET rel.name_score = vector.similarity.cosine(n.embedding[0..768],
                similar_node.embedding[0..768])"""
            tx.run(query)

    def collapse_clusters(self, min_id: int, threshold: int = 0.99):
        merge_query = f"MATCH (n) WHERE n.row_index >= {min_id}\n"\
        """WITH collect(n) AS nodes
        UNWIND nodes AS node
        CALL {
          WITH node
          MATCH (node)-[rel:Identity]->(connected)\n"""\
          f"WHERE rel.score > 0.988 and rel.name_score > 0.988\n"\
          """WITH collect(connected) AS connectedNodes, node
          CALL apoc.refactor.mergeNodes(connectedNodes + node) YIELD node AS mergedNode
          RETURN mergedNode
        } IN TRANSACTIONS OF 10 ROWS
        RETURN mergedNode"""
        self.vector_db.query(merge_query)

    @staticmethod
    def clean_up(tx, min_id: int):
        consolidate_identities = """MATCH
        (a)-[rels:Identity]->(b)\n"""\
        f"WHERE a <> b and a.row_index >= {min_id}\n"\
        """WITH a, b, rels
        ORDER BY rels.score DESC
        WITH a, b, collect(rels) AS sortedRels
        WITH a, b, sortedRels[0] AS topRelationship, sortedRels[1..] AS
        restOfRelationships
        FOREACH (rel IN restOfRelationships |
        DELETE rel
        )
        RETURN a, b, topRelationship"""

        tx.run(consolidate_identities)

        # Ensure identities are symmetric
        symmetrize = """
        MATCH (a)-[rel:Identity]->(b)
        WHERE NOT (a)<-[:Identity]-(b)
        CREATE (a)<-[newRel:Identity]-(b)
        SET newRel = rel
        """
        tx.run(symmetrize)

        clear_self_rels = """MATCH (a) -[rel:Identity]-(a)
        DELETE rel"""

        tx.run(clear_self_rels)

    @staticmethod
    def assign_neighbor_score(tx):
        query = """
        MATCH (a)-[:Contribution]->(common)-[:Contribution]-(b)-[ident:Identity]-(a)
        WHERE elementId(a) < elementId(b) and ident.score > 0.98// To avoid duplicate pairs (a, b) and (b, a)
        WITH a, b, ident, count(common) AS commonNeighbors
        MATCH (a)-[:Contribution]->(aContributions)
        WITH a, b, ident, commonNeighbors, collect(distinct aContributions) AS aContributionsList, count(distinct aContributions) AS aNeighborCount
        MATCH (b)-[:Contribution]->(bContributions)
        WITH a, b, ident, commonNeighbors, aContributionsList, aNeighborCount, collect(distinct bContributions) AS bContributionsList, count(distinct bContributions) AS bNeighborCount
        SET ident.neighbor_score = toFloat(commonNeighbors) / ((aNeighborCount + bNeighborCount))
        """
        tx.run(query)



parser = argparse.ArgumentParser()
parser.add_argument("--table-key", type=str, help="Path to table key json")
parser.add_argument("--csv-file", type=str, default=None)
parser.add_argument("--score-min", type=float,
                    help="Score threshold above which "\
                    "identity relationships will be created", default=0.97)
parser.add_argument("--name-score-min", type=float,
                    help="Name score threshold above which "\
                    "identity relationships will be created", default=0.97)
parser.add_argument("--score-collapse-min", type=float,
                    help="Score threshold above which "\
                    "identity relationships will be collapsed", default=0.99)
parser.add_argument("--name-score-collapse-min", type=float,
                    help="Name score threshold above which "\
                    "identity relationships will be collapsed", default=0.99)
parser.add_argument("--row-index", type=int,
                    help="Row index of table to start from")
args = parser.parse_args()

if __name__ == "__main__":
    embedding = EntityEmbedder()
    vector_db = Neo4jVector.from_existing_graph(embedding=embedding,
                            username=st.secrets.neo4j.user,
                            password=st.secrets.neo4j.pwd,
                            url=st.secrets.neo4j.uri,
                            node_label="Entity",
                            embedding_node_property="embedding",
                            text_node_properties = ["text"],
                            pre_delete_collection=False
                        )
    pipeline = GraphDBPipeline(vector_db, st.connection("snowflake"))
    table_key = TableDataKey(args.table_key)
    pipeline.process_snowflake_table(table_key,
                                     csv_file=args.csv_file,
                                     relationship_type=table_key.relationship_type,
                                     row_index=5100)
