from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, AIMessageChunk, ToolMessage
import streamlit as st
import uuid
import json

from agentic_chatbot import chatbot

st.title("Langraph Chatbot")

def generate_thread_id():
    return str(uuid.uuid4())

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state['chat_threads'].append(thread_id)                                   

def load_conversation(thread_id):
    state = chatbot.get_state(config={
        "configurable": {
            "thread_id": thread_id 
        }
    })
    return state.values.get("messages", [])

def load_threads():
    return list(set([ckpt.config['configurable']['thread_id'] for ckpt in chatbot.checkpointer.list(None)]))


# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state['initialized'] = True
    st.session_state['chat_threads'] = load_threads()
    
    if st.session_state['chat_threads']: 
        st.session_state['thread_id'] = st.session_state['chat_threads'][-1]
    else:
        st.session_state['thread_id'] = generate_thread_id()
        add_thread(st.session_state['thread_id'])
    
    st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])

# Sidebar UI
st.sidebar.title("Chat Threads")

if st.sidebar.button("New Thread"):
    st.session_state["thread_id"] = generate_thread_id()
    st.session_state['message_history'] = []
    add_thread(st.session_state["thread_id"])
    st.rerun()
    
for thread_id in st.session_state['chat_threads'][::-1]:
    if st.sidebar.button(f"Thread {thread_id[:8]}...", key=f"thread_{thread_id}"):
        st.session_state['thread_id'] = thread_id 
        st.session_state['message_history'] = load_conversation(thread_id)
        st.rerun()


# --- 1. RENDER HISTORY ---
messages_to_render = st.session_state['message_history']

if 'is_streaming' in st.session_state and st.session_state['is_streaming']:
    last_human_idx = -1
    for i in range(len(messages_to_render) - 1, -1, -1):
        if isinstance(messages_to_render[i], HumanMessage):
            last_human_idx = i
            break
    
    if last_human_idx >= 0:
        messages_to_render = messages_to_render[:last_human_idx]

for msg in messages_to_render:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
            
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    with st.expander(f"🔧 Tool Call: {tc['name']}", expanded=False):
                        try:
                            st.json(json.loads(tc['args']) if isinstance(tc['args'], str) else tc['args'])
                        except:
                            st.code(tc['args'])
            
            if msg.content:
                st.markdown(msg.content)
                
    elif isinstance(msg, ToolMessage):
        with st.chat_message("assistant"):
            with st.expander(f"✅ Tool Result: {msg.name}", expanded=False):
                try:
                    st.json(json.loads(msg.content) if isinstance(msg.content, str) else msg.content)
                except:
                    st.text(msg.content)


# --- 2. HANDLE NEW INPUT ---
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state['is_streaming'] = True
    
    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)

    # Create a single assistant message container for the entire response
    with st.chat_message("assistant"):
        # Container for status messages
        status_container = st.empty()
        
        # Container for tool calls/results (rendered first, above text)
        tools_container = st.container()
        
        # Container for the streaming text (rendered last, below tools)
        text_placeholder = st.empty()
        
        full_response = ""
        is_running_tools = True
        tool_results_rendered = {}  # Track which tool results we've already shown
        
        try:
            for chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                {
                    "configurable": {"thread_id": st.session_state["thread_id"]},
                    "metadata": {"thread_id": st.session_state["thread_id"]},
                    "run_name": f"ChatBot Trace of {st.session_state['thread_id']}"
                }, 
                stream_mode="messages"
            ):
                # 1. Handle AI deciding to call a tool
                if isinstance(chunk, AIMessageChunk) and chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        if tc_chunk.get("name"):
                            status_container.markdown(f"⏳ *Calling {tc_chunk['name']}...*")
                
                # 2. Handle Tool finishing execution
                elif isinstance(chunk, ToolMessage):
                    status_container.markdown(f"⚙️ *Processing {chunk.name} results...*")
                    
                    # Render tool results in the tools container (above text)
                    if chunk.name not in tool_results_rendered:
                        with tools_container:
                            with st.expander(f"✅ Tool Result: {chunk.name}", expanded=False):
                                try:
                                    content = chunk.content
                                    st.json(json.loads(content) if isinstance(content, str) else content)
                                except:
                                    st.text(chunk.content)
                        tool_results_rendered[chunk.name] = True
                
                # 3. Handle the final text response
                elif isinstance(chunk, AIMessageChunk) and chunk.content:
                    # Once text starts, clear the status
                    if is_running_tools:
                        status_container.empty()
                        is_running_tools = False
                        
                    full_response += chunk.content
                    # Stream text in the text placeholder (below tools)
                    text_placeholder.markdown(full_response + "▌")
            
            # Finalize the text display
            if full_response:
                text_placeholder.markdown(full_response)
            elif is_running_tools:
                status_container.markdown("✅ *Completed*")
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
    
    # Clean up and reload
    st.session_state['is_streaming'] = False
    st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])
    st.rerun()