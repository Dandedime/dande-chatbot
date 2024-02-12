import streamlit as st
import pinecone as pc
from conversation import SQLConversation
from utils import write_full_response, select_tables, write_message
from constants import TABLE_IDX_DICT

st.title("Andy")

# Initialize the conversation
if "conversation" not in st.session_state:
    st.session_state.conversation =\
        SQLConversation(st.connection("snowflake"), pc.Pinecone(api_key=st.secrets.PINECONE_API_KEY),
                                                    api_key=st.secrets.OPENAI_API_KEY)#, model="gpt-3.5-turbo")

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
            tables = select_tables(st.session_state.conversation)
            try:
                table_idx = [TABLE_IDX_DICT[table_name] for table_name in tables]
            except KeyError:
                message = "I couldn't find any tables relevant to your question."
                write_message(message, st.session_state.conversation)
        try: 
            write_full_response(st.session_state.conversation, table_idx)
        except Exception as e:
            message = f"Your query returned the following error: {str(e)}"
            write_message(message, st.session_state.conversation)

