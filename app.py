
import io
import re
import time
from contextlib import redirect_stdout

import streamlit as st

from agent import understand_user_query, run_agent


# --------------------------------------------------
# 1. Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="PolicyPilot AI",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------
# 2. Attractive custom UI
# --------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    .stApp {
        background:
            radial-gradient(ellipse at 15% 0%, #172554 0%, transparent 38%),
            linear-gradient(135deg, #080d1b 0%, #0c1224 55%, #11132a 100%);
        color: #eef2ff;
        font-family: 'DM Sans', sans-serif;
    }

    h1, h2, h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #f8fafc !important;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1428, #11152a);
        border-right: 1px solid #26304a;
    }

    .hero {
        padding: 28px 30px;
        border: 1px solid rgba(129, 140, 248, .32);
        border-radius: 24px;
        background: linear-gradient(
            120deg,
            rgba(49, 46, 129, .55),
            rgba(30, 41, 85, .48),
            rgba(15, 23, 42, .72)
        );
        margin-bottom: 22px;
        box-shadow: 0 15px 45px rgba(0, 0, 0, .18);
    }

    .eyebrow {
        color: #a5b4fc;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
    }

    .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: clamp(30px, 4vw, 45px);
        font-weight: 700;
        line-height: 1.15;
        margin: 12px 0;
        color: #ffffff;
    }

    .hero-description {
        color: #cbd5e1;
        font-size: 15px;
        line-height: 1.8;
        max-width: 760px;
    }

    .pill {
        display: inline-block;
        border: 1px solid #39446b;
        background: rgba(99, 102, 241, .13);
        color: #c7d2fe;
        border-radius: 999px;
        padding: 6px 11px;
        margin: 10px 6px 0 0;
        font-size: 12px;
    }

    .section-label {
        color: #a5b4fc;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1.6px;
        text-transform: uppercase;
        margin: 10px 0 12px;
    }

    .info-card {
        background: rgba(20, 29, 54, .78);
        border: 1px solid #283453;
        border-radius: 17px;
        padding: 17px;
        min-height: 115px;
    }

    .info-card .icon {
        font-size: 23px;
    }

    .info-card .heading {
        color: #f1f5f9;
        font-weight: 700;
        font-size: 15px;
        margin-top: 8px;
    }

    .info-card .description {
        color: #a8b5ce;
        font-size: 12px;
        line-height: 1.6;
        margin-top: 5px;
    }

    .answer-card {
        border: 1px solid rgba(129, 140, 248, .42);
        background: linear-gradient(
            140deg,
            rgba(30, 41, 85, .9),
            rgba(20, 29, 54, .95)
        );
        padding: 22px;
        border-radius: 19px;
        line-height: 1.85;
        color: #f1f5f9;
        margin: 12px 0;
    }

    .small-muted {
        color: #94a3b8;
        font-size: 12px;
    }

    .stButton > button {
        border-radius: 12px;
        border: 1px solid #38456b;
        background: #151e39;
        color: #e0e7ff;
        min-height: 43px;
        transition: all .2s ease;
    }

    .stButton > button:hover {
        border-color: #818cf8;
        background: #252c55;
        color: white;
    }

    .stChatInput textarea {
        color: #f8fafc !important;
    }

    [data-testid="stChatMessage"] {
        border: 1px solid rgba(71, 85, 125, .32);
        border-radius: 17px;
        background: rgba(15, 23, 42, .45);
    }

    a {
        color: #a5b4fc !important;
    }

    hr {
        border-color: #27314c;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 3. Session state
# --------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_details" not in st.session_state:
    st.session_state.last_details = None

if "last_source" not in st.session_state:
    st.session_state.last_source = None


# --------------------------------------------------
# 4. Sidebar
# --------------------------------------------------

with st.sidebar:
    st.markdown("## 🧭 PolicyPilot AI")
    st.caption("Company Policy Intelligence")

    st.markdown("---")

    st.markdown("### ⚙️ System overview")
    st.markdown(
        """
        - 🧠 **LLM:** Groq
        - 📚 **RAG:** Semantic retrieval
        - 🔎 **Search:** DuckDuckGo
        - 💾 **History:** SQLite
        - 🧬 **Embeddings:** Sentence Transformers
        """
    )

    st.markdown("---")
    st.markdown("### 🛡️ How it works")
    st.caption(
        "Understand your question → find a company document → "
        "retrieve relevant text → generate a grounded answer."
    )

    st.markdown("---")

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_details = None
        st.session_state.last_source = None
        st.rerun()

    st.markdown(
        '<p class="small-muted">AI-generated answers can be incomplete. '
        'Always verify important employment decisions against official '
        'company documents.</p>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# 5. Hero section
# --------------------------------------------------

st.markdown(
    """
    <div class="hero">
        <div class="eyebrow">✦ AI-powered employee policy research</div>
        <div class="hero-title">
            Understand your workplace.<br>
            <span style="color:#a5b4fc">Know your policies.</span>
        </div>
        <div class="hero-description">
            Ask questions about leave, salary, benefits, remote work,
            holidays and workplace rules. PolicyPilot searches available
            company sources and uses retrieved text to answer.
        </div>
        <div>
            <span class="pill">✦ Groq AI</span>
            <span class="pill">⌕ Official-source search</span>
            <span class="pill">▤ RAG grounded answers</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 6. Feature cards
# --------------------------------------------------

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        """
        <div class="info-card">
            <div class="icon">📄</div>
            <div class="heading">Policy discovery</div>
            <div class="description">
                Search for relevant public company policy documents.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        """
        <div class="info-card">
            <div class="icon">🧠</div>
            <div class="heading">Context-based answers</div>
            <div class="description">
                Generate answers from text retrieved by your RAG pipeline.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="info-card">
            <div class="icon">🔗</div>
            <div class="heading">Source transparency</div>
            <div class="description">
                Inspect the source URL and retrieved document chunks.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# 7. Quick questions
# --------------------------------------------------

st.markdown('<div class="section-label">TRY A SAMPLE QUESTION</div>',
            unsafe_allow_html=True)

quick_questions = [
    "Does Amazon provide paid sick leave?",
    "Can Microsoft employees work from home?",
    "What is Google's parental leave policy?",
    "Does Apple offer employee benefits in India?",
]

quick_cols = st.columns(2)

selected_question = None

for index, question in enumerate(quick_questions):
    with quick_cols[index % 2]:
        if st.button(
            question,
            key=f"quick_{index}",
            use_container_width=True,
        ):
            selected_question = question


# --------------------------------------------------
# 8. Process a user question through the existing agent
# --------------------------------------------------

def process_question(question: str):
    question = question.strip()

    if not question:
        return

    st.session_state.messages.append({
        "role": "user",
        "content": question,
    })

    log_buffer = io.StringIO()
    answer = ""
    details = None
    error_message = None
    start_time = time.perf_counter()

    with st.spinner(
        "Understanding your question, checking documents and generating an answer..."
    ):
        try:
            with redirect_stdout(log_buffer):
                details = understand_user_query(question)

                run_agent(
                    company=details["company"],
                    policy_type=details["policy_type"],
                    original_question=question,
                )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"

    elapsed = time.perf_counter() - start_time
    logs = log_buffer.getvalue()

    # Extract the answer printed by the current rag_chat.py.
    match = re.search(
        r"FINAL ANSWER\s*=+\s*(.*?)\s*=+",
        logs,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        answer = match.group(1).strip()

    # Fallback for saved versions of rag_chat.py without answer markers.
    if not answer:
        fallback = re.search(
            r"Answer:\s*(.*?)(?:\nRetrieved sources:|\Z)",
            logs,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if fallback:
            answer = fallback.group(1).strip()

    # Find the official source URL printed by agent.py.
    source_match = re.search(r"Source:\s*(https://\S+)", logs)
    source_url = source_match.group(1).rstrip(").,") if source_match else None

    if not answer:
        if error_message:
            answer = (
                "I couldn't complete the request. Check the error and "
                "processing details below."
            )
        elif "No matching official-domain candidates" in logs:
            answer = (
                "I couldn't find a suitable official-domain document "
                "for this question. This does not mean the company has "
                "no such policy."
            )
        elif "No accessible candidate passed" in logs:
            answer = (
                "I couldn't retrieve an accessible policy document "
                "that passed the initial relevance check."
            )
        else:
            answer = (
                "No final answer was captured. Review the processing "
                "details below to find where the request stopped."
            )

    st.session_state.last_details = details
    st.session_state.last_source = source_url

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "company": details.get("company") if details else None,
        "policy_type": details.get("policy_type") if details else None,
        "source": source_url,
        "logs": logs,
        "error": error_message,
        "elapsed": elapsed,
    })


# Handle a quick-question button.
if selected_question:
    process_question(selected_question)


# --------------------------------------------------
# 9. Chat history
# --------------------------------------------------

st.markdown("---")
st.markdown('<div class="section-label">YOUR POLICY ASSISTANT</div>',
            unsafe_allow_html=True)

for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
        else:
            st.markdown(message["content"])

            company = message.get("company")
            policy_type = message.get("policy_type")
            source = message.get("source")

            if company or policy_type:
                left, right = st.columns(2)
                with left:
                    st.caption(f"🏢 Company: {company or 'Not identified'}")
                with right:
                    st.caption(
                        f"📑 Topic: {policy_type or 'Not identified'}"
                    )

            if source:
                st.markdown(f"🔗 **Source:** [{source}]({source})")

            st.caption(
                f"⏱️ Total processing time: "
                f"{message.get('elapsed', 0):.2f} seconds"
            )

            if message.get("error"):
                st.error(message["error"])

            logs = message.get("logs", "")
            if logs:
                with st.expander("🔍 View processing details"):
                    st.code(logs, language="text")


# --------------------------------------------------
# 10. Chat input
# --------------------------------------------------

user_question = st.chat_input(
    "Ask about leave, salary, benefits, remote work..."
)

if user_question:
    process_question(user_question)
    st.rerun()


# --------------------------------------------------
# 11. Footer
# --------------------------------------------------

st.markdown("---")
st.markdown(
    """
    <div style="text-align:center;color:#8290ad;font-size:12px;padding:8px">
        PolicyPilot AI · Groq + Retrieval-Augmented Generation<br>
        Answers depend on accessible source documents and may not reflect
        every location, role or employment agreement.
    </div>
    """,
    unsafe_allow_html=True,
)
