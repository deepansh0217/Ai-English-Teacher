
import json
import json
import streamlit as st

from database import (
    init_db,
    get_or_create_user,
    get_progress,
    update_progress,
    create_conversation,
    list_conversations,
    get_conversation,
    rename_conversation,
    touch_conversation,
    save_test_result,
    get_test_results,
)
from teacher_graph import build_graph
from lessons import LESSONS, get_lesson, get_next_lesson


st.set_page_config(
    page_title="AI English Teacher",
    page_icon="📚",
    layout="wide",
)

init_db()


@st.cache_resource
def get_resources():
    result = build_graph()

    if not isinstance(result, tuple) or len(result) != 2:
        raise RuntimeError(
            "build_graph() must return (graph, connection). "
            f"Received type={type(result).__name__}, "
            f"value_count={len(result) if isinstance(result, tuple) else 'not a tuple'}"
        )

    return result


st.title("📚 AI English Teacher")
st.caption("Learn English from zero, one step at a time.")


# ---------- Learner profile ----------

with st.sidebar:
    st.header("Learner profile")

    display_name = st.text_input(
        "Your learner name",
        placeholder="Enter your name",
        key="learner_name",
    ).strip()

    st.caption("Use the same name to find your saved local progress.")

if not display_name:
    st.info("Enter your learner name in the sidebar to begin.")
    st.stop()

user_id = get_or_create_user(display_name)

# Clear the selected thread if the learner changes.
if st.session_state.get("active_user") != user_id:
    st.session_state.active_user = user_id
    st.session_state.active_thread = None
    st.session_state.pop("test_answers", None)
    st.session_state.pop("test_category", None)


try:
    graph, _connection = get_resources()
except Exception:
    import traceback

    st.error("AI teacher initialization failed:")
    st.code(traceback.format_exc())
    st.stop()

progress = get_progress(user_id)

try:
    completed_lessons = json.loads(progress["completed_lessons"])
except (ValueError, TypeError):
    completed_lessons = []


# ---------- Conversations ----------

with st.sidebar:
    st.divider()
    st.header("Your conversations")

    if st.button("➕ New conversation", use_container_width=True):
        thread_id = create_conversation(user_id)
        st.session_state.active_thread = thread_id
        st.rerun()

    conversations = list_conversations(user_id)

    if conversations:
        options = {c["thread_id"]: c["title"] for c in conversations}

        current = st.session_state.get("active_thread")
        if current not in options:
            current = None

        selected = st.selectbox(
            "Resume a saved conversation",
            options=list(options.keys()),
            index=(
                list(options.keys()).index(current)
                if current in options else None
            ),
            format_func=lambda tid: options[tid],
            placeholder="Choose a conversation",
        )

        if selected and selected != st.session_state.get("active_thread"):
            st.session_state.active_thread = selected
            st.rerun()

    if not st.session_state.get("active_thread"):
        thread_id = create_conversation(user_id)
        st.session_state.active_thread = thread_id
        st.rerun()

thread_id = st.session_state.active_thread

# Verify that the selected conversation belongs to this learner.
conversation = get_conversation(user_id, thread_id)
if conversation is None:
    st.session_state.active_thread = None
    st.rerun()

config = {"configurable": {"thread_id": thread_id}}


# ---------- Lesson panel ----------

progress = get_progress(user_id)
current_lesson = get_lesson(progress["current_lesson"])
next_lesson = get_next_lesson(current_lesson["id"])

with st.sidebar:
    st.divider()
    st.header("Current lesson")
    st.write(f"**{current_lesson['title']}**")
    st.caption(f"Level: {progress['current_level']}")
    st.write(current_lesson["objective"])

    with st.expander("Lesson explanation"):
        st.write(current_lesson["explanation"])
        for example in current_lesson["examples"]:
            st.markdown(f"- {example}")

    if st.button("Teach me this lesson", use_container_width=True):
        lesson_text = (
            f"Please teach me lesson {current_lesson['id']}: "
            f"{current_lesson['title']}. "
            f"Learning objective: {current_lesson['objective']}. "
            f"Explanation: {current_lesson['explanation']}. "
            f"Examples: {', '.join(current_lesson['examples'])}. "
            f"Teach me step by step, then ask the practice question: "
            f"{current_lesson['practice']}"
        )
        graph.invoke(
            {"messages": [{"role": "user", "content": lesson_text}]},
            config=config,
        )
        rename_conversation(
            user_id, thread_id, current_lesson["title"]
        )
        touch_conversation(user_id, thread_id)
        st.rerun()

    if next_lesson:
        if st.button("Complete lesson & continue"):
            if current_lesson["id"] not in completed_lessons:
                completed_lessons.append(current_lesson["id"])

            update_progress(
                user_id,
                next_lesson["id"],
                completed_lessons,
            )
            st.rerun()
    else:
        st.success("You reached the end of the starter curriculum!")


# ---------- Main tabs ----------

chat_tab, test_tab, progress_tab = st.tabs(
    ["💬 Teacher chat", "📝 English tests", "📈 My progress"]
)


with chat_tab:
    st.subheader("Talk to your English teacher")

    state = graph.get_state(config)
    messages = state.values.get("messages", []) if state.values else []

    for message in messages:
        role = getattr(message, "type", "")
        if role not in ("human", "ai"):
            continue

        with st.chat_message(
            "user" if role == "human" else "assistant"
        ):
            st.markdown(message.content)

    if prompt := st.chat_input("Ask a question or practise English..."):
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Your teacher is thinking..."):
                try:
                    result = graph.invoke(
                        {"messages": [{"role": "user", "content": prompt}]},
                        config=config,
                    )
                    answer = result["messages"][-1].content
                    st.markdown(answer)
                except Exception as exc:
                    st.error(f"Could not get a response: {exc}")

        if len(messages) == 0:
            rename_conversation(
                user_id, thread_id, prompt[:60]
            )

        touch_conversation(user_id, thread_id)
        st.rerun()


# ---------- Vocabulary and tense tests ----------


# ---------- Vocabulary and tense tests ----------

QUIZZES = {
    "Vocabulary": [
        {
            "q": "What does 'happy' mean?",
            "options": [
                "Feeling pleased",
                "Feeling hungry",
                "Feeling sleepy",
            ],
            "answer": 0,
            "explanation": "'Happy' means feeling pleased or glad.",
        },
        {
            "q": "What is the opposite of 'big'?",
            "options": ["Tall", "Small", "Long"],
            "answer": 1,
            "explanation": "'Small' is the opposite of 'big'.",
        },
        {
            "q": "Choose the correct word: I drink ____.",
            "options": ["water", "run", "blue"],
            "answer": 0,
            "explanation": "Water is something we can drink.",
        },
    ],
    "Tenses": [
        {
            "q": "She ___ to school every day.",
            "options": ["go", "goes", "going"],
            "answer": 1,
            "explanation": "Use 'goes' with she in the present simple.",
        },
        {
            "q": "Yesterday, I ___ football.",
            "options": ["play", "played", "playing"],
            "answer": 1,
            "explanation": "Use 'played' for this completed past action.",
        },
        {
            "q": "Right now, he ___ a book.",
            "options": ["reads", "read", "is reading"],
            "answer": 2,
            "explanation": "Use 'is reading' for an action happening now.",
        },
    ],
}


def generate_quiz(graph, category, user_id):
    model_request = (
        f"Generate a new {category} test for an English learner. "
        "Return only the required JSON."
    )

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": model_request,
                }
            ]
        },
        config={
            "configurable": {
                "thread_id": f"quiz-{user_id}-{category}"
            }
        },
    )

    content = result["messages"][-1].content.strip()

    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0].strip()

    data = json.loads(content)
    questions = data["questions"]

    if len(questions) != 3:
        raise ValueError("Expected exactly 3 questions.")

    for question in questions:
        if (
            not isinstance(question, dict)
            or not isinstance(question.get("q"), str)
            or not isinstance(question.get("options"), list)
            or len(question["options"]) != 3
            or not isinstance(question.get("answer"), int)
            or isinstance(question.get("answer"), bool)
            or not 0 <= question["answer"] < 3
            or not isinstance(question.get("explanation"), str)
        ):
            raise ValueError("Invalid quiz format.")

    return questions


with test_tab:
    st.subheader("Practice your English")

    category = st.selectbox(
        "Choose a test",
        list(QUIZZES.keys()),
    )

    quiz_key = f"quiz_{user_id}_{category}"
    version_key = f"quiz_version_{user_id}_{category}"

    # Initialize the default quiz.
    if quiz_key not in st.session_state:
        st.session_state[quiz_key] = QUIZZES[category]

    if version_key not in st.session_state:
        st.session_state[version_key] = 0

    # Reset the previous result when category changes.
    if st.session_state.get("test_category") != category:
        st.session_state.test_category = category
        st.session_state.pop("test_answers", None)
        st.session_state.pop("test_score", None)
        st.session_state.pop("test_total", None)

    # Generate a new quiz.
    if st.button("🔄 Generate new test"):
        try:
            with st.spinner("Generating a new test..."):
                new_questions = generate_quiz(
                    graph,
                    category,
                    user_id,
                )

                st.session_state[quiz_key] = new_questions
                st.session_state[version_key] += 1

                st.session_state.pop("test_answers", None)
                st.session_state.pop("test_score", None)
                st.session_state.pop("test_total", None)

            st.success("New test generated successfully!")
            st.rerun()

        except Exception as exc:
            st.error(f"Could not generate test: {exc}")

    # IMPORTANT: This form is OUTSIDE the Generate button block.
    questions = st.session_state[quiz_key]
    version = st.session_state[version_key]
    answers_key = f"answers_{user_id}_{category}_{version}"

    with st.form(f"quiz_form_{user_id}_{category}_{version}"):
        answers = []

        for index, question in enumerate(questions):
            st.markdown(
                f"**Question {index + 1}.** {question['q']}"
            )

            choice = st.radio(
                "Choose one answer",
                question["options"],
                key=f"{answers_key}_{index}",
                index=None,
            )

            answers.append(choice)

        submitted = st.form_submit_button("Submit test")

    if submitted:
        if any(answer is None for answer in answers):
            st.warning("Please answer every question before submitting.")

        else:
            score = sum(
                answer == question["options"][question["answer"]]
                for answer, question in zip(answers, questions)
            )

            save_test_result(
                user_id,
                thread_id,
                category,
                score,
                len(questions),
            )

            st.session_state.test_answers = [
                {
                    "question": question["q"],
                    "selected": answer,
                    "correct": question["options"][question["answer"]],
                    "is_correct": (
                        answer == question["options"][question["answer"]]
                    ),
                    "explanation": question["explanation"],
                }
                for answer, question in zip(answers, questions)
            ]

            st.session_state.test_score = score
            st.session_state.test_total = len(questions)
            st.rerun()

    # Display the submitted test results.
    if st.session_state.get("test_answers") is not None:
        st.divider()

        score = st.session_state.test_score
        total = st.session_state.test_total

        st.metric("Your score", f"{score}/{total}")
        st.progress(score / total)

        for index, result in enumerate(
            st.session_state.test_answers,
            start=1,
        ):
            icon = "✅" if result["is_correct"] else "❌"

            st.markdown(
                f"{icon} **Question {index}:** {result['question']}"
            )
            st.write(f"Your answer: {result['selected']}")

            if not result["is_correct"]:
                st.write(f"Correct answer: {result['correct']}")

            st.caption(result["explanation"])


# ---------- Learner progress ----------

with progress_tab:
    st.subheader("Your learning progress")

    completed_lessons = json.loads(
        get_progress(user_id)["completed_lessons"]
    )
    st.metric("Completed lessons", len(completed_lessons))
    st.write("Completed lesson IDs:", completed_lessons or "None yet")

    results = get_test_results(user_id)

    if results:
        st.subheader("Test history")
        for result in results:
            st.write(
                f"**{result['category']}** — "
                f"{result['score']}/{result['total_questions']} "
                f"({result['created_at']})"
            )
    else:
        st.info("Your test scores will appear here after your first test.")
