"""
Web server for the AI English Teacher.

database.py, lessons.py and teacher_graph.py are used exactly as they are.
This file only replaces the Streamlit part (app.py) with a small JSON API
that the HTML/CSS/JS frontend in /static talks to.

The GROQ_API_KEY is read from .env / environment variables on the SERVER
(teacher_graph.py does this). It is never sent to the browser.
"""

import json
import threading

from flask import Flask, jsonify, request, send_from_directory

from database import (
    init_db,
    connect,
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
from lessons import get_lesson, get_next_lesson

app = Flask(__name__, static_folder="static", static_url_path="/static")

init_db()
graph, _connection = build_graph()

# One shared SQLite connection is used by the graph, so run calls one by one.
graph_lock = threading.Lock()


# ---------- Default quizzes (same as app.py) ----------

QUIZZES = {
    "Vocabulary": [
        {
            "q": "What does 'happy' mean?",
            "options": ["Feeling pleased", "Feeling hungry", "Feeling sleepy"],
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

# Current quiz per (user, category). Correct answers stay on the server.
CURRENT_QUIZ = {}


def generate_quiz(category, user_id):
    model_request = (
        f"Generate a new {category} test for an English learner. "
        "Return only the required JSON."
    )

    with graph_lock:
        result = graph.invoke(
            {"messages": [{"role": "user", "content": model_request}]},
            config={"configurable": {"thread_id": f"quiz-{user_id}-{category}"}},
        )

    content = text_of(result["messages"][-1]).strip()

    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0].strip()

    questions = json.loads(content)["questions"]

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


# ---------- Helpers ----------

class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"error": err.message}), err.status


@app.errorhandler(Exception)
def handle_unexpected(err):
    app.logger.exception("Unhandled error")
    return jsonify({"error": str(err)}), 500


def text_of(message):
    content = message.content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def payload():
    return request.get_json(silent=True) or {}


def require_user(data=None):
    data = data if data is not None else payload()
    user_id = data.get("user_id") or request.args.get("user_id")

    if not user_id:
        raise ApiError("Please enter your learner name first.", 401)

    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row is None:
        raise ApiError("Learner not found. Please log in again.", 401)

    return user_id


def require_thread(user_id, thread_id):
    if not thread_id or get_conversation(user_id, thread_id) is None:
        raise ApiError("Conversation not found.", 404)
    return {"configurable": {"thread_id": thread_id}}


def completed_of(progress):
    try:
        return json.loads(progress["completed_lessons"])
    except (ValueError, TypeError):
        return []


def lesson_payload(user_id):
    progress = get_progress(user_id)
    lesson = get_lesson(progress["current_lesson"])
    return {
        "level": progress["current_level"],
        "lesson": lesson,
        "has_next": get_next_lesson(lesson["id"]) is not None,
        "completed": completed_of(progress),
    }


def public_questions(questions):
    return [{"q": q["q"], "options": q["options"]} for q in questions]


def get_quiz(user_id, category):
    if category not in QUIZZES:
        raise ApiError("Unknown test category.")
    key = (user_id, category)
    if key not in CURRENT_QUIZ:
        CURRENT_QUIZ[key] = QUIZZES[category]
    return CURRENT_QUIZ[key]


# ---------- Pages ----------

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------- Learner ----------

@app.post("/api/login")
def login():
    name = (payload().get("name") or "").strip()
    try:
        user_id = get_or_create_user(name)
    except ValueError as exc:
        raise ApiError(str(exc))
    return jsonify({"user_id": user_id, "display_name": name})


# ---------- Conversations ----------

@app.get("/api/conversations")
def conversations():
    user_id = require_user()
    return jsonify({"conversations": list_conversations(user_id)})


@app.post("/api/conversations")
def new_conversation():
    user_id = require_user()
    return jsonify({"thread_id": create_conversation(user_id)})


@app.get("/api/messages")
def messages():
    user_id = require_user()
    thread_id = request.args.get("thread_id")
    config = require_thread(user_id, thread_id)

    with graph_lock:
        state = graph.get_state(config)

    items = state.values.get("messages", []) if state.values else []
    out = []
    for message in items:
        role = getattr(message, "type", "")
        if role in ("human", "ai"):
            out.append(
                {
                    "role": "user" if role == "human" else "assistant",
                    "content": text_of(message),
                }
            )
    return jsonify({"messages": out})


@app.post("/api/chat")
def chat():
    data = payload()
    user_id = require_user(data)
    thread_id = data.get("thread_id")
    config = require_thread(user_id, thread_id)

    prompt = (data.get("message") or "").strip()
    if not prompt:
        raise ApiError("Please type a message.")

    with graph_lock:
        state = graph.get_state(config)
        is_first = not (state.values and state.values.get("messages"))
        result = graph.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
        )

    answer = text_of(result["messages"][-1])

    if is_first:
        rename_conversation(user_id, thread_id, prompt[:60])
    touch_conversation(user_id, thread_id)

    return jsonify({"answer": answer})


# ---------- Lessons ----------

@app.get("/api/lesson")
def lesson():
    user_id = require_user()
    return jsonify(lesson_payload(user_id))


@app.post("/api/lesson/teach")
def teach_lesson():
    data = payload()
    user_id = require_user(data)
    thread_id = data.get("thread_id")
    config = require_thread(user_id, thread_id)

    current = get_lesson(get_progress(user_id)["current_lesson"])
    lesson_text = (
        f"Please teach me lesson {current['id']}: {current['title']}. "
        f"Learning objective: {current['objective']}. "
        f"Explanation: {current['explanation']}. "
        f"Examples: {', '.join(current['examples'])}. "
        f"Teach me step by step, then ask the practice question: "
        f"{current['practice']}"
    )

    with graph_lock:
        graph.invoke(
            {"messages": [{"role": "user", "content": lesson_text}]},
            config=config,
        )

    rename_conversation(user_id, thread_id, current["title"])
    touch_conversation(user_id, thread_id)
    return jsonify({"ok": True})


@app.post("/api/lesson/complete")
def complete_lesson():
    user_id = require_user()
    progress = get_progress(user_id)
    completed = completed_of(progress)
    current = get_lesson(progress["current_lesson"])
    next_lesson = get_next_lesson(current["id"])

    if next_lesson is None:
        raise ApiError("You reached the end of the starter curriculum!")

    if current["id"] not in completed:
        completed.append(current["id"])

    update_progress(user_id, next_lesson["id"], completed)
    return jsonify(lesson_payload(user_id))


# ---------- Tests ----------

@app.get("/api/quiz")
def quiz():
    user_id = require_user()
    category = request.args.get("category", "Vocabulary")
    questions = get_quiz(user_id, category)
    return jsonify({"questions": public_questions(questions)})


@app.post("/api/quiz/generate")
def quiz_generate():
    data = payload()
    user_id = require_user(data)
    category = data.get("category", "Vocabulary")
    if category not in QUIZZES:
        raise ApiError("Unknown test category.")

    try:
        questions = generate_quiz(category, user_id)
    except Exception as exc:
        raise ApiError(f"Could not generate test: {exc}", 502)

    CURRENT_QUIZ[(user_id, category)] = questions
    return jsonify({"questions": public_questions(questions)})


@app.post("/api/quiz/submit")
def quiz_submit():
    data = payload()
    user_id = require_user(data)
    category = data.get("category", "Vocabulary")
    questions = get_quiz(user_id, category)
    answers = data.get("answers")

    if (
        not isinstance(answers, list)
        or len(answers) != len(questions)
        or any(
            not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < 3
            for a in answers
        )
    ):
        raise ApiError("Please answer every question before submitting.")

    results = []
    score = 0
    for answer, question in zip(answers, questions):
        correct = answer == question["answer"]
        score += int(correct)
        results.append(
            {
                "question": question["q"],
                "selected": question["options"][answer],
                "correct": question["options"][question["answer"]],
                "is_correct": correct,
                "explanation": question["explanation"],
            }
        )

    thread_id = data.get("thread_id")
    if thread_id and get_conversation(user_id, thread_id) is None:
        thread_id = None

    save_test_result(user_id, thread_id, category, score, len(questions))
    return jsonify({"score": score, "total": len(questions), "results": results})


# ---------- Progress ----------

@app.get("/api/progress")
def progress():
    user_id = require_user()
    return jsonify(
        {
            "completed": completed_of(get_progress(user_id)),
            "results": get_test_results(user_id),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
