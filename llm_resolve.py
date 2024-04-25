from conversation import ConversationOpenAI
from build_prompts import SystemPrompt
from neo4j_connection import Neo4jConnection
from typing import Tuple, List
from pathlib import Path

import re
import streamlit as st

class LLMResolver(ConversationOpenAI):

    def __init__(self,  neo4j_conn: Neo4jConnection, api_key, model="gpt-4-0125-preview",
                 memory_window=1):
        prompt = \
            SystemPrompt.from_file(Path("prompt_contexts/entity_resolution.txt"))
        super().__init__(api_key, model=model,
                         system_prompt=prompt.general_instructions,
                         memory_window=memory_window)
        self.messages = self.history.messages

    def resolve(self, entities: List[str]) -> Tuple[List[List[int]], List[float]]:
        query = [{"role": "user", "content": str(entities)}]
        print(self.messages)
        print(query)
        res = self.respond(self.messages+query)
        res = "".join([chunk.choices[0].delta.content or "" for chunk in res])
        print(res)
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
                            float = 0.98):
        query = "MATCH  p=(n)-[:Identity*]-(b)\n"\
        f"WHERE ALL(rel in relationships(p) WHERE rel.score>{threshold} and"\
        f" rel.name_score>{name_threshold}) and NOT (\n"\
          """n.middle_name is not null AND 
          b.middle_name is not null AND 
          LEFT(n.middle_name, 1) = LEFT(b.middle_name, 1)
        )
        RETURN n.name, collect(b.name)"""

        res = self.neo4j_conn.query(query, unpack=False)
        for node, matches in res:
            entities = [node.text] + [m.text for m in matches]
            clusters, scores = self.resolve(entities)
            for cluster_idx, score in zip(clusters, scores):
                if len(cluster_idx)>1:
                    query = f"MATCH p=(n {{entity_id: {node.entity_id}}})-"\
                            "[:Identity*]-(b)\n"\
                    f"WHERE ALL(rel in relationships(p) WHERE rel.score>{threshold} and"\
                    f" rel.name_score>{name_threshold}) and NOT (\n"\
                      """n.middle_name is not null AND 
                      b.middle_name is not null AND 
                      LEFT(n.middle_name, 1) = LEFT(b.middle_name, 1)
                    )
                    WITH n, collect(b) AS connectedNodes
                    UNWIND connectedNodes AS node"""
                    f"FOREACH (rel in relationships(p) | SET rel.llm_score = {score}"
                    self.neo4j_conn.query(query)


if __name__ == "__main__":
    neo4j_conn = Neo4jConnection(st.secrets.neo4j.uri, st.secrets.neo4j.user,
                                 st.secrets.neo4j.pwd)
    resolver = LLMResolver(neo4j_conn, st.secrets.OPENAI_API_KEY)
    test = ["""An individual named manoil , mark with first name of mark, last
 name of manoil; This individual has address1 of 1113 w mission ln,
 state of az, zipcode of 85021.0, occupation of attorney, employer
 of manoil time, plc""", """An individual named manoil , mark l with first name
 of mark, last name of manoil, middle name of l; This individual has
 address1 of 24 w camelback rd, address2 of ste a, state of az,
 zipcode of 85013.0, occupation of attorney, employer of manoil
 kime, plc""", """An individual named manoil , mark l with first name of mark,
 last name of manoil, middle name of l""", """An individual named manoil , mack
 m with first name of mack, last name of manoil, middle name of c;
 This individual has address1 of 24 w camelback rd, address2 of ste
 a, state of az, zipcode of 85013.0, occupation of doctor,
 employer of mayo clinic"""]
    print(resolver.resolve(test))
