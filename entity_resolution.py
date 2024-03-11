import uuid
import pinecone
import streamlit as st

from dataclasses import asdict

from data_structures import Entity, Corporation
from langchain_openai import OpenAIEmbeddings


class EntityResolution:

    def __init__(self, pinecone_index, threshold: float = 0.97, embedding=None):
        self.pinecone_index = pinecone_index
        if embedding is None:
            embedding = OpenAIEmbeddings()
        self.embedding = embedding

        self.threshold = threshold

    def resolve(self, entity_data: Entity):
        """
        Args:
            entity_data: Entity class instance containing data for entity to be
                rseolved
        Returns:
            Pinecone id either referring to an existing entity or for a newly
                upserted entity
        """
        data_str = entity_data.to_text()
        vector = self.embedding.embed_query(data_str)

        query_filter = {
            "entity_type": {"$eq": entity_data.entity_type}
        }
        best_match_entity = self.pinecone_index.query(vector=vector, top_k=1,
                                                      include_metadata=True,
                                                      filter=query_filter)

        print(best_match_entity)
        score = None
        if not len(best_match_entity["matches"]):
            matched_entity = None
            pinecone_id = self._upsert_new_entity(vector, data_str,
                                                  entity_data)
        else:
            best_match = best_match_entity["matches"][0]
            score = best_match_entity["matches"][0]["score"]
            if score  >= self.threshold:
                pinecone_id = best_match["id"]
                matched_entity = best_match["metadata"]
                matched_entity['score'] = score
            else:
                matched_entity = None
                pinecone_id = self._upsert_new_entity(vector, data_str,
                                                      entity_data)
        return matched_entity, pinecone_id, score

    def _upsert_new_entity(self, vector, text, entity):
        print("UPSERTING!")
        pinecone_id = str(uuid.uuid4().hex)
        metadata = {"text": text}
        metadata.update({key: val for key, val in asdict(entity).items() if val
                        is not None})
        print(metadata)
        self.pinecone_index.upsert(vectors=[{"id": pinecone_id, "values":
                                             vector, "metadata":
                                             metadata}])
        return pinecone_id



if __name__ == "__main__":
    pc = pinecone.Pinecone(api_key=st.secrets.PINECONE_API_KEY)
    index = pc.Index("entities")
    er = EntityResolution(index)

    hca = Corporation(name="HCA Healthcare", industry="healtchare services")
    matched, _ = er.resolve(hca)
    print(matched)
    mmm =  Corporation(name="3M", industry="salvation",
                          ownership_structure="public", hq_state="MN")
    matched, _ = er.resolve(mmm)
    print(matched)
