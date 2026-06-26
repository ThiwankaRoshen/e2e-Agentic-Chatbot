from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import interrupt, Command
import streamlit as st
import uuid
import json
import os
import tempfile

from agentic_chatbot import chatbot, load_pdf_and_create_vector_store, INDEX_PATH

st.title("Langraph Chatbot")

# ── PDF Upload Section ────────────────────────────────────────────────────────

st.sidebar.title("📄 PDF Upload")

uploaded_pdf = st.sidebar.file_uploader(
    "Upload a PDF to chat with",
    type=["pdf"],
    help="Upload a PDF document. The chatbot will use it to answer your questions via the RAG tool."
)

if uploaded_pdf is not None:
    pdf_key = f"pdf_loaded_{uploaded_pdf.name}_{uploaded_pdf.size}"

    if st.session_state.get("loaded_pdf_key") != pdf_key:
        with st.sidebar:
            with st.spinner(f"Processing **{uploaded_pdf.name}**…"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_pdf.read())
                    tmp_path = tmp.name

                try:
                    load_pdf_and_create_vector_store(tmp_path)
                    st.session_state["loaded_pdf_key"] = pdf_key
                    st.session_state["loaded_pdf_name"] = uploaded_pdf.name
                    st.success(f"✅ **{uploaded_pdf.name}** indexed successfully!")
                except Exception as e:
                    st.error(f"❌ Failed to process PDF: {e}")
                finally:
                    os.unlink(tmp_path)
    else:
        st.sidebar.success(f"✅ **{st.session_state['loaded_pdf_name']}** is loaded.")

elif st.session_state.get("loaded_pdf_name"):
    st.sidebar.info(
        f"📎 Using index from **{st.session_state['loaded_pdf_name']}**.\n\n"
        "Upload a new PDF to replace it."
    )

# ── Thread helpers ────────────────────────────────────────────────────────────

def generate_thread_id():
    return str(uuid.uuid4())

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state['chat_threads'].append(thread_id)

def load_conversation(thread_id):
    state = chatbot.get_state(config={
        "configurable": {"thread_id": thread_id}
    })
    return state.values.get("messages", [])

def load_threads():
    return list(set([
        ckpt.config['configurable']['thread_id']
        for ckpt in chatbot.checkpointer.list(None)
    ]))

def get_interrupt_data(thread_id):
    """Get interrupt data for a thread"""
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    
    # Check if we're in an interrupt state
    tasks = getattr(state, 'tasks', None)
    if tasks and len(tasks) > 0:
        # Get the first task (usually there's only one during interrupt)
        task = tasks[0]
        if hasattr(task, 'interrupts') and task.interrupts:
            return task.interrupts
    return None

def has_pending_interrupt(thread_id):
    """Check if thread has pending interrupt"""
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    return state.next == '__interrupt__' if hasattr(state, 'next') else False

# ── Session state init ────────────────────────────────────────────────────────

if 'initialized' not in st.session_state:
    st.session_state['initialized'] = True
    st.session_state['chat_threads'] = load_threads()

    if st.session_state['chat_threads']:
        st.session_state['thread_id'] = st.session_state['chat_threads'][-1]
    else:
        st.session_state['thread_id'] = generate_thread_id()
        add_thread(st.session_state['thread_id'])

    st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])

# ── Sidebar: thread controls ──────────────────────────────────────────────────

st.sidebar.title("💬 Chat Threads")

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

# ── Render chat history ───────────────────────────────────────────────────────

messages_to_render = st.session_state['message_history']

for msg in messages_to_render:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)

    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    # Don't show tool result expander for interrupted tools
                    if tc['name'] == 'purchase_stock' and has_pending_interrupt(st.session_state['thread_id']):
                        with st.expander(f"🔧 Tool Call: {tc['name']} (Waiting for approval...)", expanded=True):
                            try:
                                st.json(json.loads(tc['args']) if isinstance(tc['args'], str) else tc['args'])
                            except Exception:
                                st.code(tc['args'])
                    else:
                        with st.expander(f"🔧 Tool Call: {tc['name']}", expanded=False):
                            try:
                                st.json(json.loads(tc['args']) if isinstance(tc['args'], str) else tc['args'])
                            except Exception:
                                st.code(tc['args'])
            if msg.content:
                st.markdown(msg.content)

    elif isinstance(msg, ToolMessage):
        with st.chat_message("assistant"):
            with st.expander(f"✅ Tool Result: {msg.name}", expanded=False):
                try:
                    st.json(json.loads(msg.content) if isinstance(msg.content, str) else msg.content)
                except Exception:
                    st.text(msg.content)

# ── Check for interrupts ──────────────────────────────────────────────────────

current_thread = st.session_state['thread_id']
interrupts = get_interrupt_data(current_thread)

if interrupts:
    st.warning("⚠️ **Action Required: Approve or Decline Transaction**")
    
    for interrupt_item in interrupts:
        # Display the interrupt message
        interrupt_value = interrupt_item.value if hasattr(interrupt_item, 'value') else str(interrupt_item)
        st.info(interrupt_value)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve", key=f"approve_{current_thread}", type="primary"):
                # Resume with approval using the correct config
                chatbot.invoke(
                    Command(resume="yes"),
                    config={"configurable": {"thread_id": current_thread}}
                )
                st.session_state['message_history'] = load_conversation(current_thread)
                st.rerun()
        
        with col2:
            if st.button("❌ Decline", key=f"decline_{current_thread}"):
                # Resume with decline
                chatbot.invoke(
                    Command(resume="no"),
                    config={"configurable": {"thread_id": current_thread}}
                )
                st.session_state['message_history'] = load_conversation(current_thread)
                st.rerun()
    
    # Disable chat input when interrupt is pending
    st.chat_input(disabled=True, placeholder="Please respond to the approval request above...")

else:
    # ── Handle new user input ─────────────────────────────────────────────────────

    pdf_index_exists = os.path.exists(INDEX_PATH)

    user_input = st.chat_input("Type your message here…")

    if user_input:
        pdf_keywords = {"pdf", "document", "file", "uploaded", "attachment"}
        if not pdf_index_exists and any(kw in user_input.lower() for kw in pdf_keywords):
            st.warning(
                "⚠️ No PDF has been indexed yet. "
                "Upload a PDF in the sidebar first, then ask your question."
            )
        else:
            st.session_state['is_streaming'] = True

            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                status_container = st.empty()
                tools_container = st.container()
                text_placeholder = st.empty()

                full_response = ""
                is_running_tools = True
                tool_results_rendered = {}
                tool_calls_seen = set()

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
                        # Check if this chunk indicates an interrupt
                        if isinstance(chunk, dict) and "__interrupt__" in chunk:
                            status_container.markdown("⏳ *Waiting for your approval...*")
                            break

                        if isinstance(chunk, AIMessageChunk) and chunk.tool_call_chunks:
                            for tc_chunk in chunk.tool_call_chunks:
                                if tc_chunk.get("name"):
                                    tool_name = tc_chunk['name']
                                    if tool_name == "purchase_stock":
                                        status_container.markdown("⏳ *Waiting for your approval...*")
                                    else:
                                        status_container.markdown(f"⏳ *Calling {tool_name}…*")

                        elif isinstance(chunk, ToolMessage):
                            # Only process tool messages for non-interrupted tools
                            if chunk.name not in tool_results_rendered:
                                status_container.markdown(f"⚙️ *Processing {chunk.name} results…*")
                                with tools_container:
                                    with st.expander(f"✅ Tool Result: {chunk.name}", expanded=False):
                                        try:
                                            content = chunk.content
                                            st.json(json.loads(content) if isinstance(content, str) else content)
                                        except Exception:
                                            st.text(chunk.content)
                                tool_results_rendered[chunk.name] = True

                        elif isinstance(chunk, AIMessageChunk) and chunk.content:
                            if is_running_tools:
                                status_container.empty()
                                is_running_tools = False
                            full_response += chunk.content
                            text_placeholder.markdown(full_response + "▌")

                    # Only show completion if we actually got content and no interrupt
                    if full_response:
                        text_placeholder.markdown(full_response)
                    elif is_running_tools and not has_pending_interrupt(st.session_state['thread_id']):
                        status_container.markdown("✅ *Completed*")

                except Exception as e:
                    error_msg = str(e)
                    if "interrupt" in error_msg.lower():
                        # The stream was interrupted, which is expected for HITL
                        status_container.markdown("⏳ *Waiting for your approval...*")
                    else:
                        st.error(f"An error occurred: {error_msg}")

            st.session_state['is_streaming'] = False
            st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])
            
            # Only rerun if no interrupt pending
            if not has_pending_interrupt(st.session_state['thread_id']):
                st.rerun()
            else:
                st.rerun()