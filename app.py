## Life Coach Agent 

import os
import uuid
import asyncio
import tempfile
import streamlit as st
from openai import OpenAI
from agents import Agent, Runner, WebSearchTool, FileSearchTool, SQLiteSession

# SQLite file where the SDK stores conversation history across runs/restarts.
DB_PATH = "coach_memory.db"


# ──────────────────────────────────────────────────────────────────────────
# 0. One reusable event loop for the whole app.
#    Runner.run_sync() / asyncio.run() each spin up a brand-new event loop
#    (often on a new thread) with no Streamlit ScriptRunContext attached ->
#    "missing ScriptRunContext!" warning. Running every coroutine on a single
#    loop via run_until_complete() keeps everything on the main script thread.
# ──────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def run_async(coro):
    """Run a coroutine on the shared loop instead of asyncio.run()/run_sync()."""
    loop = get_event_loop()
    return loop.run_until_complete(coro)


# ──────────────────────────────────────────────────────────────────────────
# 1. Page setup
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Life Coach Agent", page_icon="🌱")
st.title("🌱 Life Coach Agent")
st.caption("An encouraging AI coach for motivation, self-improvement, and habits")

# Life-coach persona (system instructions).
# NOTE: the model is explicitly told to ALWAYS answer in Korean.
COACH_INSTRUCTIONS = """
You are a warm, supportive life coach. Your goal is to help the user move
toward a better life, healthier habits, and their self-improvement goals.

Guidelines:
- Always be encouraging, empathetic, and positive. Never judge or scold.
- Do not stop at vague comfort; suggest small, concrete "first steps" the
  user can take today.
- The user may upload personal goal documents or journals. When a question
  relates to their goals, plans, or progress, FIRST use the file_search tool
  to look up what they actually wrote, and reference it specifically.
- Then, when motivational content, self-improvement tips, habit-formation
  strategies, or recent research/examples would help, use the web_search
  tool and combine it with their goals to give PERSONALIZED advice.
- Track progress over time: compare the user's stated goals with how things
  are going, and gently suggest next steps.
- When you rely on search results, explain them in plain, easy language.
- Remember the earlier conversation and keep coaching across turns.

IMPORTANT: Always respond in Korean (한국어), in a friendly coaching tone.
"""


# ──────────────────────────────────────────────────────────────────────────
# 2. Build the agent. Tools depend on whether goal documents were indexed,
#    so the cache key includes the vector store id.
# ──────────────────────────────────────────────────────────────────────────
@st.cache_resource
def create_agent(model: str, vector_store_id: str | None) -> Agent:
    tools = [WebSearchTool(search_context_size="medium")]
    if vector_store_id:
        # Lets the coach search the user's uploaded goal documents.
        tools.append(
            FileSearchTool(
                vector_store_ids=[vector_store_id],
                max_num_results=3,
            )
        )
    return Agent(
        name="Life Coach",
        instructions=COACH_INSTRUCTIONS,
        model=model,
        tools=tools,
    )


# ──────────────────────────────────────────────────────────────────────────
# 3. Upload goal documents (PDF/TXT) into an OpenAI Vector Store so the
#    FileSearchTool can retrieve them.
# ──────────────────────────────────────────────────────────────────────────
def index_goal_documents(uploaded_files) -> str:
    """Create/reuse a vector store and upload+index the given files. Returns id."""
    client = OpenAI()  # reads OPENAI_API_KEY from the environment

    vector_store_id = st.session_state.get("vector_store_id")
    if not vector_store_id:
        vector_store = client.vector_stores.create(
            name=f"life-coach-goals-{st.session_state.session_id}"
        )
        vector_store_id = vector_store.id

    # Streamlit gives in-memory files; write them to disk so the SDK can
    # upload them with their real filename/extension (pdf/txt).
    tmp_dir = tempfile.mkdtemp()
    streams = []
    try:
        for f in uploaded_files:
            path = os.path.join(tmp_dir, f.name)
            with open(path, "wb") as out:
                out.write(f.getbuffer())
            streams.append(open(path, "rb"))

        # upload_and_poll blocks until ingestion/indexing finishes.
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=streams,
        )
    finally:
        for s in streams:
            s.close()

    return vector_store_id


# ──────────────────────────────────────────────────────────────────────────
# 4. Turn the agent's tool calls into the indicator lines shown in the example
#    (e.g. "[목표 문서 검색]" and '[웹 검색: "..."]').
# ──────────────────────────────────────────────────────────────────────────
def format_tool_activity(result) -> str:
    lines: list[str] = []
    for item in result.new_items:
        raw = getattr(item, "raw_item", None)
        if raw is None:
            continue
        rtype = getattr(raw, "type", None)

        if rtype == "file_search_call":
            lines.append("> 📄 목표 문서 검색")

        elif rtype == "web_search_call":
            action = getattr(raw, "action", None)
            query = getattr(action, "query", None)
            if query is None and isinstance(action, dict):
                query = action.get("query")
            lines.append(f'> 🔍 웹 검색: "{query}"' if query else "> 🔍 웹 검색")

    return ("\n".join(lines) + "\n\n") if lines else ""


# ──────────────────────────────────────────────────────────────────────────
# 5. Session state
#    - session_id      : one stable id per browser session
#    - messages        : display-only chat records
#    - vector_store_id  : id of the indexed goal documents (None until upload)
#    - indexed_files    : filenames shown in the sidebar
#    SQLiteSession handles the agent's real memory automatically.
# ──────────────────────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = f"coach-{uuid.uuid4().hex[:12]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None
if "indexed_files" not in st.session_state:
    st.session_state.indexed_files = []
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "api_key_saved" not in st.session_state:
    st.session_state.api_key_saved = False

session = SQLiteSession(st.session_state.session_id, DB_PATH)


# ──────────────────────────────────────────────────────────────────────────
# 6. Sidebar - API key / model / goal documents / reset
# ──────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")

    # Enter the OpenAI API key, then click "Save" to lock it in.
    # Once saved, the field is disabled so it can't be edited by accident.
    if not st.session_state.api_key_saved:
        key_input = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.api_key,
            help="Your key is kept only in this session's memory, not saved to disk.",
        )
        if st.button("Save API Key", use_container_width=True):
            if key_input.strip():
                st.session_state.api_key = key_input.strip()
                st.session_state.api_key_saved = True
                st.rerun()
            else:
                st.warning("Please enter a valid API key first.")
    else:
        # Locked state: input field is hidden entirely.
        st.success("API Key saved ✓")
        if st.button("Change API Key", use_container_width=True):
            st.session_state.api_key_saved = False
            st.rerun()

    # Make the saved key available to the OpenAI client / Agents SDK.
    if st.session_state.api_key:
        os.environ["OPENAI_API_KEY"] = st.session_state.api_key
    else:
        st.info("Enter your OpenAI API Key to start.")

    # Hosted web/file search require a Responses-API-capable model.
    model = st.selectbox(
        "Model",
        options=["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        index=0,
    )

    st.divider()
    st.subheader("📄 Goal documents")
    uploaded_files = st.file_uploader(
        "Upload your goals/journal (PDF or TXT)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
    )
    if st.button("Review my goals", use_container_width=True):
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Set your OpenAI API Key first.")
        elif not uploaded_files:
            st.warning("Please choose at least one PDF or TXT file.")
        else:
            with st.spinner("Your coach is reviewing your goals..."):
                try:
                    vs_id = index_goal_documents(uploaded_files)
                    st.session_state.vector_store_id = vs_id
                    st.session_state.indexed_files = sorted(
                        {f.name for f in uploaded_files}
                        | set(st.session_state.indexed_files)
                    )
                    st.success("Your coach has reviewed your goals!")
                except Exception as e:
                    st.error(f"Couldn't review your goals: {e}")

    if st.session_state.indexed_files:
        st.caption("Goals your coach has reviewed:")
        for name in st.session_state.indexed_files:
            st.caption(f"• {name}")

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        # Wipe both the on-disk chat memory and the UI history.
        try:
            run_async(session.clear_session())
        except Exception:
            pass
        st.session_state.messages = []
        st.rerun()

    st.caption(f"Session: `{st.session_state.session_id}`")


# ──────────────────────────────────────────────────────────────────────────
# 7. Re-render the existing conversation
# ──────────────────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    avatar = "🌱" if msg["role"] == "assistant" else "🧑"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])


# ──────────────────────────────────────────────────────────────────────────
# 8. Handle chat input
#    The input box stays disabled until the API key has been saved.
# ──────────────────────────────────────────────────────────────────────────
key_ready = bool(st.session_state.api_key_saved and st.session_state.api_key)

if not key_ready:
    st.info("👈 Enter and save your OpenAI API Key in the sidebar to start chatting.")

prompt = st.chat_input(
    "Ask your coach anything..." if key_ready else "Save your API Key first to start chatting",
    disabled=not key_ready,
)

if prompt:

    # (1) Show + store the user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # (2) Run the agent. session= gives it SQLite-backed memory; the vector
    #     store id (if any) wires up file search over the user's goals.
    agent = create_agent(model, st.session_state.vector_store_id)

    with st.chat_message("assistant", avatar="🌱"):
        with st.spinner("Coaching and searching..."):
            try:
                result = run_async(Runner.run(agent, prompt, session=session))

                # Show file/web search activity first, like the example
                activity = format_tool_activity(result)
                display = activity + result.final_output
            except Exception as e:
                display = f"⚠️ Something went wrong: {e}"

        st.markdown(display)

    # (3) Store assistant output for re-rendering
    st.session_state.messages.append({"role": "assistant", "content": display})