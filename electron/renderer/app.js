const API_BASE = "http://127.0.0.1:8765";

let allItems = [];       // unified list of dictations + meetings, newest first
let selectedItem = null;
let searchDebounce = null;

const el = {
  itemList: document.getElementById("item-list"),
  searchInput: document.getElementById("search-input"),
  statusPill: document.getElementById("status-pill"),
  tabRecord: document.getElementById("tab-record"),
  tabDetails: document.getElementById("tab-details"),
  tabAsk: document.getElementById("tab-ask"),
  viewRecord: document.getElementById("view-record"),
  viewDetails: document.getElementById("view-details"),
  viewAsk: document.getElementById("view-ask"),
  detailsEmpty: document.getElementById("details-empty"),
  detailsContent: document.getElementById("details-content"),
  chatMessages: document.getElementById("chat-messages"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  recIndicator: document.getElementById("rec-indicator"),
  recIndicatorTime: document.getElementById("rec-indicator-time"),
  recordTitle: document.getElementById("record-title"),
  recordToggle: document.getElementById("record-toggle"),
  recordStatus: document.getElementById("record-status"),
};

// ---------- Tabs ----------

function setTab(tab) {
  el.tabRecord.classList.toggle("active", tab === "record");
  el.tabDetails.classList.toggle("active", tab === "details");
  el.tabAsk.classList.toggle("active", tab === "ask");
  el.viewRecord.classList.toggle("active", tab === "record");
  el.viewDetails.classList.toggle("active", tab === "details");
  el.viewAsk.classList.toggle("active", tab === "ask");
}

el.tabRecord.addEventListener("click", () => setTab("record"));
el.tabDetails.addEventListener("click", () => setTab("details"));
el.tabAsk.addEventListener("click", () => setTab("ask"));

// ---------- Status ----------

async function pollHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (resp.ok) {
      el.statusPill.textContent = "ready";
      el.statusPill.className = "status-pill ok";
      return true;
    }
  } catch (e) {
    // server not up yet
  }
  el.statusPill.textContent = "connecting…";
  el.statusPill.className = "status-pill";
  return false;
}

async function waitForServerThenLoad() {
  const ready = await pollHealth();
  if (ready) {
    loadItems();
  } else {
    setTimeout(waitForServerThenLoad, 1000);
  }
}

// ---------- Sidebar list ----------

function normalizeDictation(d) {
  return {
    type: "dictation",
    id: d.timestamp,
    title: d.text.length > 60 ? d.text.slice(0, 60) + "…" : d.text,
    date: d.date,
    timeLabel: d.time,
    sortKey: d.timestamp,
    raw: d,
  };
}

function normalizeMeeting(m) {
  const started = new Date(m.started_at);
  return {
    type: "meeting",
    id: m.id,
    title: m.title || "Untitled Meeting",
    date: started.toISOString().slice(0, 10),
    timeLabel: started.toTimeString().slice(0, 5),
    sortKey: m.started_at,
    raw: m,
  };
}

async function loadItems() {
  try {
    const [dictRes, meetRes] = await Promise.all([
      fetch(`${API_BASE}/dictations`),
      fetch(`${API_BASE}/meetings`),
    ]);
    const dictations = await dictRes.json();
    const meetings = await meetRes.json();
    allItems = [
      ...dictations.map(normalizeDictation),
      ...meetings.map(normalizeMeeting),
    ].sort((a, b) => (a.sortKey < b.sortKey ? 1 : -1));
    renderList(allItems);
  } catch (e) {
    el.statusPill.textContent = "offline";
    el.statusPill.className = "status-pill error";
  }
}

function renderList(items) {
  el.itemList.innerHTML = "";
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = "Nothing here yet.";
    el.itemList.appendChild(empty);
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "item" + (selectedItem && selectedItem.id === item.id ? " selected" : "");
    row.innerHTML = `
      <div class="item-title"></div>
      <div class="item-meta">
        <span class="item-type-badge ${item.type}">${item.type}</span>
        <span>${item.date} ${item.timeLabel}</span>
      </div>
    `;
    row.querySelector(".item-title").textContent = item.title;
    row.addEventListener("click", () => selectItem(item));
    el.itemList.appendChild(row);
  }
}

function selectItemById(id) {
  const item = allItems.find((i) => i.id === id);
  if (item) selectItem(item);
}

function selectItem(item) {
  selectedItem = item;
  renderList(currentFilteredItems || allItems);
  renderDetails(item);
  setTab("details");
}

let currentFilteredItems = null;

// ---------- Search (hybrid semantic + keyword via the API) ----------

el.searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  const query = el.searchInput.value.trim();
  if (!query) {
    currentFilteredItems = null;
    renderList(allItems);
    return;
  }
  searchDebounce = setTimeout(() => runSearch(query), 250);
});

async function runSearch(query) {
  try {
    const resp = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}&k=20`);
    const results = await resp.json();
    const seenIds = new Set();
    const matched = [];
    for (const r of results) {
      if (seenIds.has(r.source_id)) continue;
      seenIds.add(r.source_id);
      const item = allItems.find((i) => i.id === r.source_id);
      if (item) matched.push(item);
    }
    currentFilteredItems = matched;
    renderList(matched);
  } catch (e) {
    // leave the list as-is on error
  }
}

// ---------- Details view ----------

function renderDetails(item) {
  el.detailsEmpty.hidden = true;
  el.detailsContent.hidden = false;

  if (item.type === "dictation") {
    el.detailsContent.innerHTML = `
      <h1>Dictation</h1>
      <div class="details-meta">${item.date} at ${item.timeLabel}</div>
      <div class="details-section">
        <div class="details-body"></div>
      </div>
    `;
    el.detailsContent.querySelector(".details-body").textContent = item.raw.text;
    return;
  }

  // meeting
  const m = item.raw;
  const durationMin = Math.round(m.duration_seconds / 60);
  let html = `
    <h1></h1>
    <div class="details-meta">${item.date} at ${item.timeLabel} — ${durationMin} min</div>
  `;
  if (m.summary) {
    html += `<div class="details-section"><h2>Summary</h2><div class="details-body summary-body"></div></div>`;
  }
  if (m.notes && m.notes.length) {
    html += `<div class="details-section"><h2>Notes</h2><div class="notes-body"></div></div>`;
  }
  if (m.transcript_segments && m.transcript_segments.length) {
    // Collapsed by default when there's a summary to lead with (progressive
    // disclosure); expanded if the transcript is the only content to show.
    const openAttr = m.summary ? "" : "open";
    html += `
      <details class="details-section transcript-toggle" ${openAttr}>
        <summary class="transcript-summary">Transcript (${m.transcript_segments.length} segments)</summary>
        <div class="details-body transcript-body"></div>
      </details>
    `;
  }
  el.detailsContent.innerHTML = html;
  el.detailsContent.querySelector("h1").textContent = item.title;
  if (m.summary) {
    el.detailsContent.querySelector(".summary-body").textContent = m.summary;
  }
  if (m.notes && m.notes.length) {
    const notesBody = el.detailsContent.querySelector(".notes-body");
    for (const n of m.notes) {
      const row = document.createElement("div");
      row.className = "note-row";
      row.innerHTML = `<span class="tag"></span><span></span>`;
      row.querySelector(".tag").textContent = n.tag || "";
      row.querySelectorAll("span")[1].textContent = n.text;
      notesBody.appendChild(row);
    }
  }
  if (m.transcript_segments && m.transcript_segments.length) {
    const text = m.transcript_segments.map((s) => s.text).join("\n\n");
    el.detailsContent.querySelector(".transcript-body").textContent = text;
  }
}

// ---------- Ask / Chat ----------

function appendChatMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `chat-msg ${role}`;
  const textEl = document.createElement("div");
  textEl.className = "answer-text";
  textEl.textContent = text;
  wrap.appendChild(textEl);
  el.chatMessages.appendChild(wrap);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  return { wrap, textEl };
}

function appendSourceChips(wrap, sources) {
  if (!sources || sources.length === 0) return;
  const chipsWrap = document.createElement("div");
  chipsWrap.className = "chat-sources";
  const seen = new Set();
  for (const s of sources) {
    if (seen.has(s.source_id)) continue;
    seen.add(s.source_id);
    const chip = document.createElement("span");
    chip.className = "source-chip";
    chip.textContent = `${s.source_title} · ${s.source_date}`;
    chip.addEventListener("click", () => selectItemById(s.source_id));
    chipsWrap.appendChild(chip);
  }
  wrap.appendChild(chipsWrap);
}

el.chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = el.chatInput.value.trim();
  if (!question) return;
  el.chatInput.value = "";

  const emptyState = el.chatMessages.querySelector(".chat-empty");
  if (emptyState) emptyState.remove();

  appendChatMessage("user", question);
  const { wrap, textEl } = appendChatMessage("assistant", "");
  textEl.classList.add("chat-thinking");
  textEl.textContent = "Thinking…";

  try {
    const resp = await fetch(`${API_BASE}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, k: 6 }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let sources = [];
    let firstDelta = true;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.sources) {
          sources = event.sources;
        } else if (event.delta) {
          if (firstDelta) {
            textEl.classList.remove("chat-thinking");
            textEl.textContent = "";
            firstDelta = false;
          }
          answer += event.delta;
          textEl.textContent = answer;
          el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
        }
      }
    }
    if (!answer) {
      textEl.classList.remove("chat-thinking");
      textEl.textContent = "(no answer)";
    }
    appendSourceChips(wrap, sources);
  } catch (e) {
    textEl.classList.remove("chat-thinking");
    textEl.textContent = `Error: ${e.message}`;
  }
});

// ---------- Record ----------

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

let isRecording = false;
let recordActionInFlight = false;

async function pollRecordingStatus() {
  try {
    const resp = await fetch(`${API_BASE}/meetings/current`);
    const status = await resp.json();
    isRecording = !!status.is_recording;

    if (isRecording) {
      const durationLabel = formatDuration(status.duration_seconds);
      el.recIndicator.hidden = false;
      el.recIndicatorTime.textContent = durationLabel;
      el.recordStatus.textContent = `Recording "${status.title}" — ${durationLabel}`;
      el.recordTitle.disabled = true;
      if (!recordActionInFlight) {
        el.recordToggle.textContent = "■ Stop Recording";
        el.recordToggle.classList.add("recording");
        el.recordToggle.disabled = false;
      }
    } else {
      el.recIndicator.hidden = true;
      el.recordTitle.disabled = false;
      if (!recordActionInFlight) {
        el.recordToggle.textContent = "● Start Recording";
        el.recordToggle.classList.remove("recording");
        el.recordToggle.disabled = false;
        el.recordStatus.textContent = "Not recording.";
      }
    }
  } catch (e) {
    // API not up yet — leave the panel in its last known state.
  }
}

el.recordToggle.addEventListener("click", async () => {
  recordActionInFlight = true;
  el.recordToggle.disabled = true;
  try {
    if (isRecording) {
      el.recordStatus.textContent = "Stopping — transcribing and summarizing locally, this can take a bit…";
      const resp = await fetch(`${API_BASE}/meetings/stop`, { method: "POST" });
      if (!resp.ok) throw new Error(await resp.text());
      el.recordTitle.value = "";
      await loadItems();
      const finished = await resp.json();
      selectItemById(finished.id);
    } else {
      const title = el.recordTitle.value.trim();
      const resp = await fetch(`${API_BASE}/meetings/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title || "Meeting" }),
      });
      if (!resp.ok) throw new Error(await resp.text());
    }
  } catch (e) {
    el.recordStatus.textContent = `Error: ${e.message}`;
  } finally {
    recordActionInFlight = false;
    await pollRecordingStatus();
  }
});

setInterval(pollRecordingStatus, 1000);
pollRecordingStatus();

// ---------- Init ----------

waitForServerThenLoad();
