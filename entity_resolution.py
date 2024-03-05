import uuid

from data import Entity
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
        vector = self.embed_query(data_str)
        best_match_entity = self.pinecone_index.query(vector=vector, top_k=1)
        if best_match_entity[0]["score"] >= self.threshold:
            pinecone_id = best_match_entity[0]["id"]
        else:
            pinecone_id = str(uuid.uuid4().hex())
            metadata = {"text": data_str}
            self.pinecone_index.upsert(vectors=[{"id": pinecone_id, "values":
                                                 vector, "metadata":
                                                 metadata}])
        return pinecone_id

    #potentially some llm verificatino stuff?

