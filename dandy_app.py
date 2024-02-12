import streamlit as st
from conversation import SQLConversation
from utils import write_full_response, select_tables, write_response

st.title("Andy")
TABLE_IDX_DICT = {"VIOLATIONS":0, "CANDIDATES":1, "ELECTION_CONTRIBUTIONS": 2, "PACS_TO_CANDIDATES": 3}

# Initialize the conversation
if "conversation" not in st.session_state:
    st.session_state.conversation = SQLConversation(st.connection("snowflake"), api_key=st.secrets.OPENAI_API_KEY, model="gpt-3.5-turbo") #model="gpt-4-0125-preview"

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
                message = "No tables are relevant to the user question"
                resp_container = st.empty()
                resp_container.markdown(message)
                response_msg = {"role": "assistant", "content": message}
                st.session_state.conversation.history.append(response_msg)
       
        write_full_response(st.session_state.conversation, table_idx)

