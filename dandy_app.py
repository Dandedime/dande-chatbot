import streamlit as st
from conversation import SQLConversation
from utils import write_full_response

st.title("Andy")

# Initialize the conversation
if "conversation" not in st.session_state:
    st.session_state.conversation = SQLConversation(st.connection("snowflake"), api_key=st.secrets.OPENAI_API_KEY, model="gpt-3.5-turbo")

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
    with st.chat_message("assistant"):
        write_full_response(st.session_state.conversation)
