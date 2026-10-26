"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  userId: null,
  name: "",
  threadId: null,
  busy: false,
};

/* ---------- Helpers ---------- */

async function api(path, { method = "GET", body, params } = {}) {
  const url = new URL(path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }

  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function renderMarkdown(text) {
  if (window.marked && window.DOMPurify) {
    return DOMPurify.sanitize(marked.parse(text, { breaks: true }));
  }
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML.replace(/\n/g, "<br>");
}

function scrollChat() {
  const box = $("#messages");
  box.scrollTop = box.scrollHeight;
}

function setBusy(busy) {
  state.busy = busy;
  ["#sendBtn", "#teachBtn", "#completeBtn", "#newConvBtn"].forEach((id) => {
    $(id).disabled = busy;
  });
}

/* ---------- Login ---------- */

async function login(name) {
  const data = await api("/api/login", { method: "POST", body: { name } });
  state.userId = data.user_id;
  state.name = data.display_name;
  localStorage.setItem("learnerName", state.name);

  $("#whoName").textContent = state.name;
  $("#login").hidden = true;
  $("#app").hidden = false;

  await loadLesson();
  await loadConversations(true);
}

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#loginError");
  err.hidden = true;
  try {
    await login($("#nameInput").value);
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  }
});

$("#logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("learnerName");
  location.reload();
});

/* ---------- Conversations ---------- */

async function loadConversations(openFirst = false) {
  const { conversations } = await api("/api/conversations", {
    params: { user_id: state.userId },
  });

  if (openFirst) {
    if (conversations.length) {
      state.threadId = conversations[0].thread_id;
    } else {
      await createConversation(false);
      return loadConversations();
    }
  }

  const list = $("#convList");
  list.innerHTML = "";
  conversations.forEach((c) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = c.title;
    btn.title = c.title;
    if (c.thread_id === state.threadId) btn.setAttribute("aria-current", "true");
    btn.addEventListener("click", () => openConversation(c.thread_id));
    li.appendChild(btn);
    list.appendChild(li);
  });

  if (openFirst) await loadMessages();
}

async function createConversation(refresh = true) {
  const { thread_id } = await api("/api/conversations", {
    method: "POST",
    body: { user_id: state.userId },
  });
  state.threadId = thread_id;
  if (refresh) {
    await loadConversations();
    await loadMessages();
  }
}

async function openConversation(threadId) {
  state.threadId = threadId;
  document.body.classList.remove("menu-open");
  switchTab("chat");
  await loadConversations();
  await loadMessages();
}

$("#newConvBtn").addEventListener("click", async () => {
  document.body.classList.remove("menu-open");
  switchTab("chat");
  await createConversation();
});

/* ---------- Chat ---------- */

function addMessage(role, text, extraClass = "") {
  const box = $("#messages");
  const empty = box.querySelector(".empty");
  if (empty) empty.remove();

  const div = document.createElement("div");
  div.className = `msg ${role} ${extraClass}`.trim();

  if (role === "assistant" && !extraClass) {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }

  box.appendChild(div);
  scrollChat();
  return div;
}

function addTyping() {
  const div = addMessage("assistant", "");
  div.innerHTML =
    '<span class="typing" aria-label="Your teacher is thinking"><i></i><i></i><i></i></span>';
  return div;
}

async function loadMessages() {
  const box = $("#messages");
  box.innerHTML = "";

  const { messages } = await api("/api/messages", {
    params: { user_id: state.userId, thread_id: state.threadId },
  });

  if (!messages.length) {
    box.innerHTML =
      '<p class="empty">Say hello to your teacher, or press “Teach me this lesson” to begin.</p>';
    return;
  }

  messages.forEach((m) => addMessage(m.role, m.content));
}

async function sendChat(text) {
  if (state.busy || !text.trim()) return;
  setBusy(true);

  addMessage("user", text);
  const typing = addTyping();

  try {
    const { answer } = await api("/api/chat", {
      method: "POST",
      body: { user_id: state.userId, thread_id: state.threadId, message: text },
    });
    typing.remove();
    addMessage("assistant", answer);
    await loadConversations();
  } catch (ex) {
    typing.remove();
    addMessage("assistant", `Could not get a response: ${ex.message}`, "error");
  } finally {
    setBusy(false);
  }
}

const chatInput = $("#chatInput");

function autoGrow() {
  chatInput.style.height = "auto";
  chatInput.style.height = `${chatInput.scrollHeight}px`;
}

chatInput.addEventListener("input", autoGrow);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chatForm").requestSubmit();
  }
});

$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = chatInput.value;
  chatInput.value = "";
  autoGrow();
  sendChat(text);
});

/* ---------- Lesson panel ---------- */

async function loadLesson() {
  const data = await api("/api/lesson", { params: { user_id: state.userId } });
  const { lesson } = data;

  $("#lessonTitle").textContent = lesson.title;
  $("#lessonLevel").textContent = data.level;
  $("#lessonObjective").textContent = lesson.objective;
  $("#lessonExplain").textContent = lesson.explanation;

  const ul = $("#lessonExamples");
  ul.innerHTML = "";
  lesson.examples.forEach((ex) => {
    const li = document.createElement("li");
    li.textContent = ex;
    ul.appendChild(li);
  });

  $("#completeBtn").hidden = !data.has_next;
  $("#curriculumDone").hidden = data.has_next;
}

$("#teachBtn").addEventListener("click", async () => {
  if (state.busy) return;
  document.body.classList.remove("menu-open");
  switchTab("chat");
  setBusy(true);

  const typing = addTyping();
  try {
    await api("/api/lesson/teach", {
      method: "POST",
      body: { user_id: state.userId, thread_id: state.threadId },
    });
    await loadMessages();
    await loadConversations();
  } catch (ex) {
    typing.remove();
    addMessage("assistant", `Could not start the lesson: ${ex.message}`, "error");
  } finally {
    setBusy(false);
  }
});

$("#completeBtn").addEventListener("click", async () => {
  if (state.busy) return;
  setBusy(true);
  try {
    await api("/api/lesson/complete", {
      method: "POST",
      body: { user_id: state.userId },
    });
    await loadLesson();
  } catch (ex) {
    alert(ex.message);
  } finally {
    setBusy(false);
  }
});

/* ---------- Tabs ---------- */

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.setAttribute("aria-selected", String(t.dataset.tab === name));
  });
  ["chat", "test", "progress"].forEach((n) => {
    $(`#tab-${n}`).hidden = n !== name;
  });

  if (name === "test") loadQuiz();
  if (name === "progress") loadProgress();
  if (name === "chat") scrollChat();
}

document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => switchTab(t.dataset.tab));
});

$("#menuBtn").addEventListener("click", () => {
  document.body.classList.toggle("menu-open");
});

/* ---------- Tests ---------- */

function showQuizMessage(text, warn = false) {
  const el = $("#quizMsg");
  el.textContent = text;
  el.className = warn ? "notice warn" : "notice";
  el.hidden = !text;
}

function renderQuiz(questions) {
  const form = $("#quizForm");
  form.innerHTML = "";
  $("#quizResult").hidden = true;
  showQuizMessage("");

  questions.forEach((q, i) => {
    const fs = document.createElement("fieldset");
    fs.className = "question";

    const legend = document.createElement("legend");
    legend.textContent = `Question ${i + 1}. ${q.q}`;
    fs.appendChild(legend);

    q.options.forEach((opt, j) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `q${i}`;
      input.value = j;
      label.appendChild(input);
      label.appendChild(document.createTextNode(opt));
      fs.appendChild(label);
    });

    form.appendChild(fs);
  });

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn primary";
  submit.textContent = "Submit test";
  form.appendChild(submit);
}

async function loadQuiz() {
  try {
    const { questions } = await api("/api/quiz", {
      params: { user_id: state.userId, category: $("#categorySelect").value },
    });
    renderQuiz(questions);
  } catch (ex) {
    showQuizMessage(ex.message, true);
  }
}

$("#categorySelect").addEventListener("change", loadQuiz);

$("#genQuizBtn").addEventListener("click", async () => {
  const btn = $("#genQuizBtn");
  btn.disabled = true;
  btn.textContent = "Generating a new test...";
  try {
    const { questions } = await api("/api/quiz/generate", {
      method: "POST",
      body: { user_id: state.userId, category: $("#categorySelect").value },
    });
    renderQuiz(questions);
    showQuizMessage("New test generated successfully!");
  } catch (ex) {
    showQuizMessage(ex.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate new test";
  }
});

$("#quizForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const form = e.target;
  const count = form.querySelectorAll("fieldset").length;
  const answers = [];

  for (let i = 0; i < count; i++) {
    const picked = form.querySelector(`input[name="q${i}"]:checked`);
    if (!picked) {
      showQuizMessage("Please answer every question before submitting.", true);
      return;
    }
    answers.push(Number(picked.value));
  }

  try {
    const data = await api("/api/quiz/submit", {
      method: "POST",
      body: {
        user_id: state.userId,
        thread_id: state.threadId,
        category: $("#categorySelect").value,
        answers,
      },
    });
    showQuizMessage("");
    renderResult(data);
  } catch (ex) {
    showQuizMessage(ex.message, true);
  }
});

function renderResult({ score, total, results }) {
  const box = $("#quizResult");
  box.innerHTML = "";

  const s = document.createElement("div");
  s.className = "score";
  s.textContent = `Your score: ${score}/${total}`;
  box.appendChild(s);

  const bar = document.createElement("div");
  bar.className = "bar";
  const fill = document.createElement("span");
  fill.style.width = `${(score / total) * 100}%`;
  bar.appendChild(fill);
  box.appendChild(bar);

  results.forEach((r, i) => {
    const item = document.createElement("div");
    item.className = `result-item ${r.is_correct ? "ok" : "no"}`;

    const lines = [
      [`${r.is_correct ? "Correct" : "Incorrect"} – Question ${i + 1}: ${r.question}`, "strong"],
      [`Your answer: ${r.selected}`, ""],
    ];
    if (!r.is_correct) lines.push([`Correct answer: ${r.correct}`, ""]);
    lines.push([r.explanation, "why"]);

    lines.forEach(([text, cls]) => {
      const p = document.createElement("p");
      if (cls === "strong") {
        const b = document.createElement("strong");
        b.textContent = text;
        p.appendChild(b);
      } else {
        p.textContent = text;
        if (cls) p.className = cls;
      }
      item.appendChild(p);
    });

    box.appendChild(item);
  });

  box.hidden = false;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Progress ---------- */

async function loadProgress() {
  const { completed, results } = await api("/api/progress", {
    params: { user_id: state.userId },
  });

  $("#completedCount").textContent = completed.length;
  $("#completedIds").textContent = completed.length ? completed.join(", ") : "None yet";

  const list = $("#history");
  list.innerHTML = "";
  $("#historyEmpty").hidden = results.length > 0;

  results.forEach((r) => {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = r.category;
    const when = document.createElement("span");
    when.className = "when";
    when.textContent = ` ${r.created_at}`;
    li.appendChild(strong);
    li.append(` – ${r.score}/${r.total_questions}`);
    li.appendChild(when);
    list.appendChild(li);
  });
}

/* ---------- Start ---------- */

(async function init() {
  const saved = localStorage.getItem("learnerName");
  if (saved) {
    try {
      await login(saved);
      return;
    } catch (_) {
      localStorage.removeItem("learnerName");
    }
  }
  $("#nameInput").focus();
})();
