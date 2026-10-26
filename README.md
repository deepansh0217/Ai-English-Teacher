ZeroToFluent

An AI English teacher that takes learners from the alphabet to confident conversation, one small lesson at a time.

Features
Guided lessons based on a 9-stage learning workflow
Chat with an AI teacher that corrects mistakes kindly
Vocabulary and tenses tests with AI-generated questions
Saved conversations and progress for every learner
Tech stack

Flask, LangGraph, LangChain, Groq, SQLite, HTML/CSS/JavaScript

Project structure
├── server.py          # Flask API + serves the frontend
├── database.py        # SQLite users, conversations, progress, tests
├── lessons.py         # Lesson content
├── teacher_graph.py   # LangGraph teacher and quiz generator
├── requirements.txt
└── static/
    ├── index.html
    ├── style.css
    └── script.js
