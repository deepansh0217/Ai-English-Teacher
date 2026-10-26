
LESSONS = [
    {
        "id": "A0-01",
        "title": "Greetings",
        "level": "A0",
        "objective": "Learn basic greetings.",
        "explanation": (
            "Hello is a greeting. Good morning is used "
            "in the morning. Goodbye is used when leaving."
        ),
        "examples": [
            "Hello!",
            "Good morning!",
            "How are you?",
            "I am fine, thank you.",
            "Goodbye!",
        ],
        "practice": "How can you greet someone in the morning?",
    },
    {
        "id": "A0-02",
        "title": "Introducing Yourself",
        "level": "A0",
        "objective": "Introduce yourself using simple sentences.",
        "explanation": (
            "Use 'My name is ...' to tell someone your name. "
            "Use 'I am ...' to describe yourself."
        ),
        "examples": [
            "My name is Rahul.",
            "I am a student.",
            "I am from India.",
        ],
        "practice": "Write one sentence to introduce yourself.",
    },
    {
        "id": "A0-03",
        "title": "The Verb Be",
        "level": "A0",
        "objective": "Use am, is, and are.",
        "explanation": (
            "Use am with I, is with he/she/it, and are with "
            "you/we/they in simple present sentences."
        ),
        "examples": [
            "I am happy.",
            "She is a teacher.",
            "They are students.",
        ],
        "practice": "Complete this sentence: I ___ happy.",
    },
]


def get_lesson(lesson_id):
    for lesson in LESSONS:
        if lesson["id"] == lesson_id:
            return lesson
    return LESSONS[0]


def get_next_lesson(current_lesson_id):
    lesson_ids = [lesson["id"] for lesson in LESSONS]

    try:
        index = lesson_ids.index(current_lesson_id)
    except ValueError:
        return LESSONS[0]

    if index + 1 < len(LESSONS):
        return LESSONS[index + 1]

    return None
