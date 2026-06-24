from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import streamlit as st
import uuid

from agentic_chatbot import chatbot

st.title("Langraph Chatbot")

def generate_thread_id():
    return str(uuid.uuid4())

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state['chat_threads'].append(thread_id)                                   
                                       

def load_conversation(thread_id):
    state = chatbot.get_state(config= {
                                        "configurable": {
                                            "thread_id": thread_id 
                                        }
                                    })
    return [{"role": "user" if isinstance(msg, HumanMessage) else "assistant", "content": msg.content} for msg in state.values.get("messages", [])]

def load_threads():
    return list(set([ckpt.config['configurable']['thread_id'] for ckpt in chatbot.checkpointer.list(None)]))


if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] =  load_threads()
    if st.session_state['chat_threads']: 
        st.session_state['thread_id'] = st.session_state['chat_threads'][-1]
        st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])
    else:
        st.session_state['thread_id'] = generate_thread_id()
        st.session_state['message_history'] = []
        add_thread(st.session_state['thread_id'])
    
    st.rerun()
    

st.sidebar.title("Chat Threads")

if st.sidebar.button("New Thread"):
    st.session_state["thread_id"] = generate_thread_id()
    st.session_state['message_history'] = []
    add_thread(st.session_state["thread_id"])
    st.rerun()
    
for thread_id in st.session_state['chat_threads'][::-1]:
    if st.sidebar.button(f"Thread {thread_id}"):
        st.session_state['thread_id'] = thread_id 
        st.session_state['message_history'] = load_conversation(thread_id)
        st.rerun()
            
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
                                                                                {
                                                                                    "configurable": {
                                                                                        "thread_id": st.session_state["thread_id"]
                                                                                    },
                                                                                    "metadata": {
                                                                                        "thread_id": st.session_state["thread_id"]
                                                                                    },
                                                                                    "run_name": f"ChatBot Trace of { st.session_state["thread_id"]}"
                                                                                }, 
                                                                                stream_mode="messages"
                                                                                ) 
                                                                            )

    st.session_state['message_history'].append({"role": "user", "content": user_input})
    st.session_state['message_history'].append({"role": "assistant", "content": response})
        
