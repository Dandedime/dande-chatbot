from conversation import ConversationOpenAI
from build_prompts import SystemPrompt
from neo4j_connection import Neo4jConnection
from typing import Tuple, List, Optional
from pathlib import Path

import re
import streamlit as st
import argparse

class LLMResolver(ConversationOpenAI):

    def __init__(self,  neo4j_conn: Neo4jConnection, api_key, azure_endpoint,
                 api_version, model="entity_resolution",
                 memory_window=1):
        self.neo4j_conn = neo4j_conn
        prompt = \
            SystemPrompt.from_file(Path("prompt_contexts/entity_resolution.txt"))
        super().__init__(api_key, azure_endpoint, api_version, model=model,
                         system_prompt=prompt.general_instructions,
                         memory_window=memory_window)
        self.messages = self.history.messages

    def resolve(self, entities: List[str]) -> Tuple[List[List[int]], List[float]]:
        query = [{"role": "user", "content": str(entities)}]
        res = self.respond(self.messages+query)
        res = "".join([chunk.choices[0].delta.content or "" for chunk in res if
                       len(chunk.choices)])
        cluster_idxs, cluster_scores = self._extract_clusters(res)
        return cluster_idxs, cluster_scores

    def _extract_clusters(self, res: str) -> Tuple[List[List[int]],
                                                   List[float]]:
        pattern = "Clusters: (\[\[.*\]\])"
        clusters = re.search(pattern, res)
        if clusters is not None:
            clusters = eval(clusters.group(1))

        pattern = "Scores: (\[.*\])"
        scores = re.search(pattern, res)
        if scores is not None:
            scores = eval(scores.group(1))

        return clusters, scores


    def resolve_db_entities(self, threshold: float = 0.98, name_threshold:
                            float = 0.98,
                            neighbor_threshold: Optional[float] = None):

        query = "MATCH  p=(n)-[rel:Identity]-(b)\n"\
        f"WHERE rel.score>{threshold} and"\
        f" rel.name_score>{name_threshold} and NOT (\n"\
          """n.middle_name is not null AND 
          b.middle_name is not null AND 
          LEFT(n.middle_name, 1) = LEFT(b.middle_name, 1)
          )"""
        if neighbor_threshold is not None:
            query += f" and rel.neighbor_score > {neighbor_threshold}\n"
        query += "RETURN n, collect(b);"""

        res = self.neo4j_conn.query(query)
        for node, matches in res:
            entities = [node] + matches
            entities_text = [n["text"] for n in entities]
            clusters, scores = self.resolve(entities_text)
            for cluster_idx, score in zip(clusters, scores):
                if len(cluster_idx)>1:
                    node_ids = [entities[i]["entity_id"] for i in cluster_idx]
                    with self.neo4j_conn._Neo4jConnection__driver.session() as session:
                        session.execute_write(self.add_llm_scores, node_ids,
                                              threshold, name_threshold,
                                              neighbor_threshold, score)

    @staticmethod
    def add_llm_scores(tx, node_ids, threshold, name_threshold,
                       neighbor_threshold, score):
        query = f"MATCH p=(n)-"\
                "[rel:Identity]-(b)\n"\
        f"WHERE n.entity_id IN {node_ids} and"\
        f" b.entity_id IN {node_ids} and rel.score>{threshold} and"\
        f" rel.name_score>{name_threshold} and NOT (\n"\
          """n.middle_name is not null AND 
          b.middle_name is not null AND 
          LEFT(n.middle_name, 1) = LEFT(b.middle_name, 1)
        )"""\
        f"SET rel.llm_score={score}"
        tx.run(query)


parser = argparse.ArgumentParser()
parser.add_argument("--score-min", type=float,
                    help="Score threshold above which "\
                    "identity relationships will be considered by the LLM",
                    default=0.97)
parser.add_argument("--name-score-min", type=float,
                    help="Name score threshold above which "\
                    "identity relationships will be considered by the LLM",
                    default=0.97)
parser.add_argument("--neighbor-score-min", type=float,
                    help="Neighbor score threshold above which "\
                    "identity relationships will be considered by the LLM",
                    default=None)
args = parser.parse_args()

if __name__ == "__main__":
    neo4j_conn = Neo4jConnection(st.secrets.neo4j.uri, st.secrets.neo4j.user,
                                 st.secrets.neo4j.pwd)
    resolver = LLMResolver(neo4j_conn, st.secrets.azure.api_key,
                           st.secrets.azure.endpoint,
                           st.secrets.azure.api_version)
    resolver.resolve_db_entities(threshold=args.score_min,
                                 name_threshold=args.name_score_min,
                                 neighbor_threshold=args.neighbor_score_min)
