import streamlit as st
from rag import PineconeIndex
from conversation import SQLConversation, PineconeConversation
import string
from typing import List

def write_full_response(conversation: SQLConversation, table_selection = None):
    """Create the full response, including query and explanation, results of the query, and the answer to the original question"""
    query_explanation = conversation.write_query(table_selection)
    response = write_response(query_explanation, conversation)
    if len(conversation.history.user_messages)>0:
        query, results, status = conversation.execute_query(response)

        if results is not None and not results.empty:
            st.dataframe(results)
            _ = write_response(conversation.answer(query, results), conversation)
        elif results is not None and results.empty:
            user_message = conversation.history.user_messages[-1]
            st.dataframe(results)
            _ = write_response(conversation.empty(user_message, query, results), conversation)
        if status is not None:
            user_message = conversation.history.user_messages[-1]
            _ = write_response(conversation.error(user_message, query, status), conversation)

def select_tables(conversation: SQLConversation):
    user_message = conversation.history.user_messages[-1]
    query_explanation = conversation.select_tables(user_message)
    response = ""
    for chunk in query_explanation:
        response += (chunk.choices[0].delta.content or "")
    response = [x.lstrip(" ").lstrip(".").rstrip(".") for x in response.split(",")]
    return [s.translate(str.maketrans('', '', ",")) for s in response]

def find_pinecone_match(conversation: PineconeConversation, query: str, candidates: List[str]):
    query_explanation = conversation.find_match(query, candidates)
    response = ""
    for chunk in query_explanation:
        response += (chunk.choices[0].delta.content or "")
    response = [x for x in response if x in "0123456789"]
    return "".join(response)
    
def write_response(generator, conversation, results=None):
    """Construct response from the generator and append to conversation history"""
    response = ""
    resp_container = st.empty()
    for chunk in generator:
        response += (chunk.choices[0].delta.content or "")
        resp_container.markdown(response)
    response_msg = {"role": "assistant", "content": response}
    if results is not None:
        response_msg["results"] = results
    conversation.history.append(response_msg)
    return response

def write_message(message, conversation):
    resp_container = st.empty()
    resp_container.markdown(message)
    response_msg = {"role": "assistant", "content": message}
    conversation.history.append(response_msg)
