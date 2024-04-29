from typing import List, Tuple
from langchain_community.embeddings import HuggingFaceEmbeddings
import re
import numpy as np


class EntityEmbedder(HuggingFaceEmbeddings):

    @staticmethod
    def _split_name_and_desc(doc: str) -> Tuple[str, str]:
        """Split doc into a piece giving the name of the entity and a piece
        describing properties of the entity"""
        pieces = doc.split('; ')
        if len(pieces) != 2:
            return doc, doc
        else:
            pieces = [pieces[0], '; '.join(pieces[1:])]
            return pieces

    def embed_documents(self, docs: List[str], name_weight: float = 3.,
                        desc_weight: float = 1.) -> List[np.array]:
        """Embeds the name and desription separately, then concatenates them
        applying the given weights"""
        if len(docs) > 0:
            name_docs, desc_docs = zip(*[self._split_name_and_desc(doc) for doc in
                                         docs])

            name_vecs = np.array(super().embed_documents(name_docs))
            desc_vecs = np.array(super().embed_documents(desc_docs))

            vecs = np.concatenate([name_weight * name_vecs,
                                   desc_weight * desc_vecs], axis=-1)
            vecs = vecs / np.linalg.norm(vecs, axis=-1, keepdims=True)
            return vecs
        else:
            return []

