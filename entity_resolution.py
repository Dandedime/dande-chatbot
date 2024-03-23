import time
import uuid
import pinecone
import streamlit as st
import numpy as np

from data_structures import Entity, Corporation, Individual, from_data_dict
from dataclasses import asdict
from abc import ABC, abstractmethod

from langchain_openai import OpenAIEmbeddings
from dataclasses import asdict
from conversation import ConversationOpenAI, PineconeConversation
from utils import find_pinecone_match
import streamlit as st

class Embedding:
    def __init__(self, field_weights=None):
        self.embedding = OpenAIEmbeddings()
        self.field_weights = field_weights

    def embed_fields(self, field_vals):
        fields, values = zip(*[(key, value) for key, value in field_vals.items()
                              if value is not None])
        vectors = np.array(self.embedding.embed_documents(values))
        norm = np.sum([self.field_weights[field] for field in fields])
        return list(map(float, (np.sum([self.field_weights[field] * vector for field, vector in
                       zip(fields, vectors)], axis=0) /
                    norm)))

class AbstractEntityResolution(ABC):
    def __init__(self, pinecone_index, min_threshold=0.95, num_matches=10, embedding=None):
        self.pinecone_index = pinecone_index
        if embedding is None:
            embedding = OpenAIEmbeddings()
        self.embedding = embedding
        self.min_threshold = min_threshold
        self.num_matches = num_matches

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
    
    def update_metadata(self, metadata, pinecone_id, data_dict):
        """If new entity has fields best match doesn't update best match's metadata with new fields"""        
        missing_keys = [k for k in data_dict.keys() if k not in metadata.keys()]
        if missing_keys:
            to_add = {k: data_dict[k] for k in missing_keys if data_dict[k] is not None}
            updated_dict = {**metadata, **to_add}
            del updated_dict["text"]
            entity = from_data_dict(updated_dict)
            to_add["text"] = entity.to_text()  
            self.pinecone_index.update(
                id=pinecone_id, 
                set_metadata=to_add
            )
            

    def resolve(self, entity_data: Entity, use_llm: bool = False, top_k: int = 1):
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
        best_match_entities = self.pinecone_index.query(vector=vector, top_k=top_k,
                                                      include_metadata=True,
                                                      filter=query_filter)
        score = None
        if not len(best_match_entities["matches"]):
            metadata = None
            pinecone_id = self._upsert_new_entity(vector, data_str,
                                                  entity)

        else:
            best_match, score = self.find_best_match(best_match_entities, data_str, top_k, use_llm)
                    
            if best_match:
                metadata = best_match["metadata"]
                pinecone_id = best_match["id"]
                self.update_metadata(metadata, pinecone_id, data_dict)

                metadata['score'] = score
                    
            else:
                metadata = None
                pinecone_id = self._upsert_new_entity(vector, data_str,
                                                    entity_data)
        return metadata, pinecone_id, score


    def _construct_filters(self, entity_data):
        query_filter = {
            "entity_type": {"$eq": entity_data.entity_type},
        }
        if entity_data.suffix is not None:
            query_filter["suffix"] = {"$in": [entity_data.suffix, "None"]}
        if entity_data.gender is not None:
            query_filter["gender"] = {"$in": [entity_data.gender, "None"]}
        return query_filter

    def _upsert_new_entity(self, vector, text, entity):
        pinecone_id = str(uuid.uuid4().hex)
        metadata = {"text": text}
        metadata.update({key: val for key, val in asdict(entity).items() if val
                        is not None})
        self.pinecone_index.upsert(vectors=[{"id": pinecone_id, "values":
                                             vector, "metadata":
                                             metadata}])
        return pinecone_id
    @abstractmethod
    def choose_best_match(self, entity, matches):
        ...


class EntityResolution(AbstractEntityResolution):

    def __init__(self, pinecone_index, num_matches=10, 
                 min_threshold: float = 0.98, embedding=None):
        super().__init__(pinecone_index=pinecone_index,
                         min_threshold=min_threshold, embedding=embedding)

    def choose_best_match(self, entity: Entity, matches):
        """
        Args:
            entity_data: Entity class instance containing data for entity to be
                rseolved
        Returns:
            Pinecone id either referring to an existing entity or for a newly
                upserted entity """
        pinecone_id = matches[0]["id"]
        matched_entity = matches[0]["metadata"]
        matched_entity["score"] = matches[0]["score"]
        return pinecone_id, matched_entity

    def cluster_entities(self, query_entity, matches, fields=None):
        data = {0: asdict(query_entity)}
        data.update({i+1: match["metadata"] for i, match in
                     enumerate(matches)})
        duplicates = deduper.partition(data)
        if len(duplicates[0][0]) > 1:
            return matches[duplicates[0][0][1]], duplicates[0][0][1]
        else:
            return None, None


class GraphDeduper(AbstractEntityResolution):
    def __init__(self, pinecone_index, neo4j_conn, min_threshold: float = 0.5,
                 embedding=None, update_graphdb: bool = True):
        self.neo4j_conn = neo4j_conn
        self.update_graphdb = update_graphdb
        super().__init__(pinecone_index=pinecone_index,
                         min_threshold=min_threshold, embedding=embedding)

    def _get_shared_edges(self, id1, id2):
        pass

    def choose_best_match(self, entity, matches):
        pass

    def merge_nodes(self, id1, id2):
        # should also merge in pinecone!
        pass

    def resolve(self, entity: Entity):
        pinecone_id, matched_entity = super().resolve(entity)
        if self.update_graphdb:
            self.merge_nodes(self, id1, id2)




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
