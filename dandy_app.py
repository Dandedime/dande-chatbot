import streamlit as st
import pinecone as pc
import sys
from conversation import SQLConversation, Neo4jConversation
from utils import write_full_response, select_tables, write_message
from constants import TABLE_IDX_DICT
from neo4j_connection import Neo4jConnection

st.title("Andy")

# Initialize the conversation
if "conversation" not in st.session_state:
    if len(sys.argv) > 1:
        db = sys.argv[1]
    else:
        db = "neo4j"
    if db == "sql":
        st.session_state.conversation =\
            SQLConversation(st.connection("snowflake"), pc.Pinecone(api_key=st.secrets.PINECONE_API_KEY),
                                                        api_key=st.secrets.azure.api_key,
                            azure_endpoint=st.secrets.azure.endpoint,
                            api_version=st.secrets.azure.api_version)
    elif db == "neo4j":
        neo4j_conn = Neo4jConnection(st.secrets.neo4j.uri, st.secrets.neo4j.user,
                                     st.secrets.neo4j.pwd)
        st.session_state.conversation =\
            Neo4jConversation(neo4j_conn, api_key=st.secrets.azure.api_key,
                              azure_endpoint=st.secrets.azure.endpoint,
                              api_version=st.secrets.azure.api_version)

# Ask for user input
if prompt := st.chat_input():
    st.session_state.conversation.history.append({"role": "user", "content": prompt})

# Display all messages
for message in st.session_state.conversation.history.messages:
    if message["role"] == "system":
        continue
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if "results" in message:
            st.dataframe(message["results"])

# Ask the assistant for a response
if st.session_state.conversation.history[-1]["role"] != "assistant":
    table_idx = None
    with st.chat_message("assistant"):
        if st.session_state.conversation.history[-1]["role"] == "user":
            if isinstance(st.session_state.conversation, SQLConversation):
                tables = select_tables(st.session_state.conversation)
                try:
                    table_idx = [TABLE_IDX_DICT[table_name] for table_name in tables]
                except KeyError:
                    message = "I couldn't find any tables relevant to your question."
                    write_message(message, st.session_state.conversation)
            else:
                table_idx = None
        try: 
            write_full_response(st.session_state.conversation, table_idx)
        except Exception as e:
            message = f"Your query returned the following error: {str(e)}"
            write_message(message, st.session_state.conversation)

