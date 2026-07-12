from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Command
import streamlit as st
import asyncio
import uuid
import json
import os
import tempfile

from app.agent import create_chatbot_agent, load_pdf_and_create_vector_store, INDEX_PATH

st.title("Langraph Chatbot")

# ── Async plumbing ─────────────────────────────────────────────────────────────
# One event loop for the whole app process, reused across every Streamlit rerun.
# Do NOT use asyncio.run() per-call here -- it tears the loop down each time,
# which orphans the aiosqlite connection the checkpointer holds onto.
import asyncio
import threading

@st.cache_resource
def get_event_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop

def run_async(coro):
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

def stream_sync(async_gen):
    """Drain an async generator using the persistent loop, yielding items
    to sync code as soon as each is ready (keeps incremental UI updates)."""
    loop = get_event_loop()
    while True:
        try:
            future = asyncio.run_coroutine_threadsafe(async_gen.__anext__(), loop)
            yield future.result()
        except StopAsyncIteration:
            break

@st.cache_resource
def get_chatbot():
    # Built once per server process, on the cached loop above.
    return run_async(create_chatbot_agent())

chatbot = get_chatbot()

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

async def _load_conversation(thread_id):
    state = await chatbot.aget_state(config={"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])

def load_conversation(thread_id):
    return run_async(_load_conversation(thread_id))

async def _load_threads():
    thread_ids = set()
    async for ckpt in chatbot.checkpointer.alist(None):
        thread_ids.add(ckpt.config['configurable']['thread_id'])
    return list(thread_ids)

def load_threads():
    return run_async(_load_threads())

async def _get_interrupt_data(thread_id):
    """
    Return the interrupt's `.value` payload for a thread, or None if there's
    no pending interrupt. The value has the shape:
        {"action_requests": [...], "review_configs": [...]}
    where action_requests[i] corresponds 1:1 with review_configs[i], and the
    decisions list you resume with must be in the same order.
    """
    state = await chatbot.aget_state(config={"configurable": {"thread_id": thread_id}})

    tasks = getattr(state, 'tasks', None)
    if tasks:
        for task in tasks:
            task_interrupts = getattr(task, 'interrupts', None)
            if task_interrupts:
                # There is normally exactly one Interrupt per task, whose
                # .value bundles all action_requests needing review.
                return task_interrupts[0].value
    return None

def get_interrupt_data(thread_id):
    return run_async(_get_interrupt_data(thread_id))

def has_pending_interrupt(thread_id):
    """Check if thread has a pending interrupt awaiting resume."""
    return get_interrupt_data(thread_id) is not None

async def _submit_decisions(thread_id, decisions):
    await chatbot.ainvoke(
        Command(resume={"decisions": decisions}),
        config={"configurable": {"thread_id": thread_id}}
    )

def submit_decisions(thread_id, decisions):
    """Resume the graph with a list of decisions, one per action_request, in order."""
    run_async(_submit_decisions(thread_id, decisions))

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

current_thread = st.session_state['thread_id']
pending_interrupt = get_interrupt_data(current_thread)

messages_to_render = st.session_state['message_history']

for msg in messages_to_render:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)

    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] == 'purchase_stock' and pending_interrupt:
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

if pending_interrupt:
    st.warning("⚠️ **Action Required: Review pending tool call(s)**")

    action_requests = pending_interrupt.get('action_requests', [])
    review_configs = pending_interrupt.get('review_configs', [])

    decisions_key = f"decisions_{current_thread}"
    if decisions_key not in st.session_state:
        st.session_state[decisions_key] = {}

    for i, action in enumerate(action_requests):
        review_config = review_configs[i] if i < len(review_configs) else {}
        allowed = review_config.get('allowed_decisions', ['approve', 'reject'])

        st.markdown(f"**Tool:** `{action.get('name', 'unknown')}`")
        st.json(action.get('arguments', {}))
        if action.get('description'):
            st.caption(action['description'])

        choice = st.radio(
            "Decision",
            options=[d for d in ["approve", "reject"] if d in allowed],
            key=f"radio_{current_thread}_{i}",
            horizontal=True,
        )

        reject_message = ""
        if choice == "reject":
            reject_message = st.text_input(
                "Reason (sent back to the model)",
                value="User rejected this action. Do not retry this tool call.",
                key=f"reject_msg_{current_thread}_{i}",
            )

        if choice == "approve":
            st.session_state[decisions_key][i] = {"type": "approve"}
        else:
            st.session_state[decisions_key][i] = {"type": "reject", "message": reject_message}

        st.divider()

    if st.button("Submit Decisions", type="primary", key=f"submit_{current_thread}"):
        decisions = [
            st.session_state[decisions_key].get(i, {"type": "reject", "message": "No decision provided."})
            for i in range(len(action_requests))
        ]
        submit_decisions(current_thread, decisions)
        del st.session_state[decisions_key]
        st.session_state['message_history'] = load_conversation(current_thread)
        st.rerun()

    st.chat_input(disabled=True, placeholder="Please respond to the approval request above...")

else:
    # ── Handle new user input ─────────────────────────────────────────────────

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

                try:
                    agen = chatbot.astream(
                        {"messages": [HumanMessage(content=user_input)]},
                        {
                            "configurable": {"thread_id": st.session_state["thread_id"]},
                            "metadata": {"thread_id": st.session_state["thread_id"]},
                            "run_name": f"ChatBot Trace of {st.session_state['thread_id']}"
                        },
                        stream_mode="messages"
                    )

                    for chunk, metadata in stream_sync(agen):
                        if isinstance(chunk, AIMessageChunk) and chunk.tool_call_chunks:
                            for tc_chunk in chunk.tool_call_chunks:
                                if tc_chunk.get("name"):
                                    tool_name = tc_chunk['name']
                                    if tool_name == "purchase_stock":
                                        status_container.markdown("⏳ *Waiting for your approval...*")
                                    else:
                                        status_container.markdown(f"⏳ *Calling {tool_name}…*")

                        elif isinstance(chunk, ToolMessage):
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

                    if has_pending_interrupt(st.session_state['thread_id']):
                        status_container.markdown("⏳ *Waiting for your approval...*")
                    elif full_response:
                        text_placeholder.markdown(full_response)
                    else:
                        status_container.markdown("✅ *Completed*")

                except Exception as e:
                    st.error(f"An error occurred: {e}")

            st.session_state['is_streaming'] = False
            st.session_state['message_history'] = load_conversation(st.session_state['thread_id'])
            st.rerun()