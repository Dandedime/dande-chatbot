import pinecone as pc
import streamlit as st
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone


class PineconeIndex:
    def __init__(self, db_conn: pc.Pinecone, index_name):
        self.index = db_conn.Index(index_name)
        self.embedding = OpenAIEmbeddings(api_key=st.secrets.OPENAI_API_KEY)
        self.vectorstore = Pinecone(self.index, self.embedding, "text")

    def get_similiar(self, query, k=10):
        res = self.vectorstore.similarity_search(query, k=k)
        return [r.page_content for r in res]

