## Life Coach Agent 

import os
import uuid
import asyncio
import streamlit as st
from dotenv import load_dotenv
from agents import Agent, Runner, WebSearchTool, SQLiteSession

# Load variables from .env into the process environment (e.g. OPENAI_API_KEY).
# Safe to call even if .env doesn't exist; existing env vars are not overridden.
load_dotenv()

# SQLite file where the SDK stores conversation history across runs/restarts.
DB_PATH = "coach_memory.db"


# ──────────────────────────────────────────────────────────────────────────
# 0. One reusable event loop for the whole app.
#    Runner.run_sync() / asyncio.run() each spin up a brand-new event loop
#    (often on a new thread), and that thread has no Streamlit
#    ScriptRunContext attached -> triggers the
#    "missing ScriptRunContext!" warning. Running every coroutine on a
#    single loop via run_until_complete() keeps everything on the main
#    Streamlit script thread instead.
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
- Whenever motivational content, self-improvement tips, habit-formation
  strategies, or recent research/examples would help, actively use the
  web_search tool to give evidence-based advice.
- When you rely on search results, explain them in plain, easy language.
- Remember the earlier conversation and keep coaching the user's goals,
  situation, and progress across turns.

IMPORTANT: Always respond in Korean (한국어), in a friendly coaching tone.
"""


# ──────────────────────────────────────────────────────────────────────────
# 2. Build the agent once and reuse it
# ──────────────────────────────────────────────────────────────────────────
@st.cache_resource
def create_agent(model: str) -> Agent:
    """Create the Agent with a hosted web search tool."""
    return Agent(
        name="Life Coach",
        instructions=COACH_INSTRUCTIONS,
        model=model,
        tools=[WebSearchTool(search_context_size="medium")],
    )


# ──────────────────────────────────────────────────────────────────────────
# 3. Pull web search queries out of the run result
#    (hosted web search -> ToolCallItem.raw_item is a ResponseFunctionWebSearch,
#     whose `action.query` holds the search string)
# ──────────────────────────────────────────────────────────────────────────
def extract_search_queries(result) -> list[str]:
    queries: list[str] = []
    for item in result.new_items:
        raw = getattr(item, "raw_item", None)
        if raw is None or getattr(raw, "type", None) != "web_search_call":
            continue
        action = getattr(raw, "action", None)
        query = getattr(action, "query", None)
        if query is None and isinstance(action, dict):
            query = action.get("query")
        if query:
            queries.append(query)
    return queries


def format_search_lines(queries: list[str]) -> str:
    """Render the search queries the way the example shows them."""
    return "".join(f'> 🔍 웹 검색: "{q}"\n' for q in queries)


# ──────────────────────────────────────────────────────────────────────────
# 4. Session memory (SQLite)
#    - session_id : one stable id per browser session
#    - SQLiteSession: the SDK reads/writes conversation history to DB_PATH
#      automatically on every Runner.run, so no manual to_input_list() needed
#    - messages   : display-only records for re-rendering the chat UI
# ──────────────────────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = f"coach-{uuid.uuid4().hex[:12]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

session = SQLiteSession(st.session_state.session_id, DB_PATH)


# ──────────────────────────────────────────────────────────────────────────
# 5. Sidebar - API key / model / reset
# ──────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")

    env_key_present = bool(os.getenv("OPENAI_API_KEY"))

    if env_key_present:
        # Key already loaded from .env (via load_dotenv()) -> nothing to type.
        st.success("OpenAI API Key loaded from .env")
    else:
        # Fallback for local/manual testing only. This is NOT written to
        # disk or to .env; it only lives in this process's environment for
        # the current run, so prefer .env for normal use.
        manual_key = st.text_input(
            "OpenAI API Key (no .env found)",
            type="password",
            help="Add OPENAI_API_KEY=sk-... to a .env file to avoid typing this every time.",
        )
        if manual_key:
            os.environ["OPENAI_API_KEY"] = manual_key

    # Hosted web search requires a Responses-API-capable model.
    model = st.selectbox(
        "Model",
        options=["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        index=0,
    )

    if st.button("Clear conversation", use_container_width=True):
        # Wipe both the on-disk memory for this session and the UI history.
        try:
            run_async(session.clear_session())
        except Exception:
            pass
        st.session_state.messages = []
        st.rerun()

    st.caption(f"Session: `{st.session_state.session_id}`")


# ──────────────────────────────────────────────────────────────────────────
# 6. Re-render the existing conversation
# ──────────────────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    avatar = "🌱" if msg["role"] == "assistant" else "🧑"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])


# ──────────────────────────────────────────────────────────────────────────
# 7. Handle chat input
# ──────────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask your coach anything..."):

    if not os.getenv("OPENAI_API_KEY"):
        st.error("Please enter your OpenAI API Key in the sidebar first.")
        st.stop()

    # (1) Show + store the user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # (2) Run the agent. Passing session= lets the SDK load past turns from
    #     SQLite and append this turn automatically -> memory is handled for us.
    #     Using run_async() keeps this on the main Streamlit thread (see note
    #     above) instead of Runner.run_sync(), which spawns a separate thread.
    agent = create_agent(model)

    with st.chat_message("assistant", avatar="🌱"):
        with st.spinner("Coaching and searching..."):
            try:
                result = run_async(Runner.run(agent, prompt, session=session))

                # Show the web search queries first, like the example
                search_lines = format_search_lines(extract_search_queries(result))
                answer = result.final_output
                display = (search_lines + "\n" if search_lines else "") + answer
            except Exception as e:
                display = f"⚠️ Something went wrong: {e}"

        st.markdown(display)

    # (3) Store assistant output for re-rendering
    st.session_state.messages.append({"role": "assistant", "content": display})