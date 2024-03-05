import uuid
import pinecone
import streamlit as st

from data import Entity, Corporation
from langchain_openai import OpenAIEmbeddings


class EntityResolution:

    def __init__(self, pinecone_index, threshold: float = 0.9, embedding=None):
        self.pinecone_index = pinecone_index
        if embedding is None:
            embedding = OpenAIEmbeddings()
        self.embedding = embedding

        self.threshold = threshold

    def resolve(self, entity_data: Entity, upsert: bool = False):
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
        best_match_entity = self.pinecone_index.query(vector=vector, top_k=1,
                                                      include_metadata=True)
        if best_match_entity["matches"][0]["score"] >= self.threshold:
            matched_entity = best_match_entity["matches"][0]
            pinecone_id = matched_entity["id"]
        else:
            matched_entity = None
            if upsert:
                pinecone_id = str(uuid.uuid4().hex())
                metadata = {"text": data_str}
                self.pinecone_index.upsert(vectors=[{"id": pinecone_id, "values":
                                                     vector, "metadata":
                                                     metadata}])
            else:
                pinecone_id = None
        return matched_entity, pinecone_id

    #potentially some llm verificatino stuff?


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
