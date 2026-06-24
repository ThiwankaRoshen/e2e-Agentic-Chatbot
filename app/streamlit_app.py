from langchain_core.messages import BaseMessage, HumanMessage
import streamlit as st


from agentic_chatbot import chatbot

st.title("Langraph Chatbot")

config = {
        "configurable":{"thread_id": "thread1"}
    }
if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

for message in st.session_state['message_history']:
    with st.chat_message(message["role"]):
        st.text(message["content"])

user_input = st.chat_input("Type your message here...")

if user_input:
    with st.chat_message("user"):
        st.text(user_input)

    

    with st.chat_message("assistant"):
        response = st.write_stream(
                        message_chunk.content for message_chunk, metadata in chatbot.stream(
                                                                                { "messages" : [HumanMessage(content=user_input)]},
                                                                                config, 
                                                                                stream_mode="messages"
                                                                                ) 
                                                                            )

    st.session_state['message_history'].append({"role": "user", "content": user_input})
    st.session_state['message_history'].append({"role": "assistant", "content": response})
        
