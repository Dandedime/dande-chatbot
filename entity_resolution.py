import uuid
import pinecone
import streamlit as st

from data_structures import Entity, Corporation, Individual, from_type
from langchain_openai import OpenAIEmbeddings
from dataclasses import asdict
from conversation import ConversationOpenAI, PineconeConversation
from utils import find_pinecone_match
import streamlit as st

class EntityResolution:

    def __init__(self, pinecone_index, threshold: float = 0.97, embedding=None):
        self.pinecone_index = pinecone_index
        if embedding is None:
            embedding = OpenAIEmbeddings()
        self.embedding = embedding

        self.threshold = threshold
        self.pinecone_conversation = PineconeConversation(api_key=st.secrets.OPENAI_API_KEY)
        
    def find_best_match(self, best_match_entity, data_str: str, top_k: int, use_llm: bool = False):
        """Either use an llm or a threshold on pinecone cosine similarity to match entities"""
        best_match = None
        score = None
        if use_llm: 
            candidates = [candidate["metadata"]["text"] for candidate in best_match_entity["matches"]]
            numbered_candidates = ""
            for idx, candidate in enumerate(candidates):
                numbered_candidates += f"\n{idx}. {candidate}"
                
            match = find_pinecone_match(self.pinecone_conversation, data_str, numbered_candidates)
            
            if match:
                match_idx = int(match)
                if match_idx < top_k:
                    best_match = best_match_entity["matches"][match_idx]
                    score = best_match_entity["matches"][match_idx]["score"]

        else: 
            best_match_candidate = best_match_entity["matches"][0]
            score = best_match_entity["matches"][0]["score"]
            if score  >= self.threshold:
                best_match = best_match_candidate
        
        return best_match, score


    def resolve(self, entity_data: Entity, use_llm: bool = True, top_k: int = 1):
        """
        Args:
            entity_data: Entity class instance containing data for entity to be
                rseolved
            use_llm: whether to use an llm to do entity resolution
            top_k: number of candidate vectors to return from pinecone
        Returns:
            Pinecone id either referring to an existing entity or for a newly
                upserted entity
        """
        data_str = entity_data.to_text()
        vector = self.embedding.embed_query(data_str)
        data_dict = asdict(entity_data)
        data_dict = {k:v for k,v in data_dict.items() if v is not None}

        query_filter = {
            "entity_type": {"$eq": entity_data.entity_type}
        }
        best_match_entity = self.pinecone_index.query(vector=vector, top_k=top_k,
                                                      include_metadata=True,
                                                      filter=query_filter)
        score = None
        if not len(best_match_entity["matches"]):
            matched_entity = None
            pinecone_id = self._upsert_new_entity(vector, data_str,
                                                  entity_data)
        else:
            best_match, score = self.find_best_match(best_match_entity, data_str, top_k, use_llm)
                    
            if best_match:
                pinecone_id = best_match["id"]
                matched_entity = best_match["metadata"]
                
                missing_keys = [k for k in data_dict.keys() if k not in matched_entity.keys()]
                if missing_keys:
                    #update metadata with missing keys
                    to_add = {k: data_dict[k] for k in missing_keys if data_dict[k] is not None}
                    updated_dict = {**matched_entity, **to_add}
                    del updated_dict["text"]
                    entity = from_type(updated_dict)
                    to_add["text"] = entity.to_text()  
                    self.pinecone_index.update(
                        id=pinecone_id, 
                        set_metadata=to_add
                    )
                    
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
        self.pinecone_index.upsert(vectors=[{"id": pinecone_id, "values":
                                             vector, "metadata":
                                             metadata}])
        return pinecone_id



if __name__ == "__main__":
    pc = pinecone.Pinecone(api_key=st.secrets.PINECONE_API_KEY)
    index = pc.Index("entities")
    er = EntityResolution(index)

    hca = Corporation(name="HCA Healthcare", industry="healtcare services", entity_type="corporation")
    matched, _, _ = er.resolve(hca)
    print(matched)
    mmm =  Corporation(name="3M", industry="salvation",
                          ownership_structure="public", hq_state="MN", entity_type="corporation")
    matched, _, _ = er.resolve(mmm)
    print(matched)
