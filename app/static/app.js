const questionEl = document.getElementById("question");
const answerEl = document.getElementById("answer");
const sourcesEl = document.getElementById("sources");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");
const askBtn = document.getElementById("askBtn");
const searchBtn = document.getElementById("searchBtn");

function setLoading(isLoading, message = "") {
  askBtn.disabled = isLoading;
  searchBtn.disabled = isLoading;
  statusEl.textContent = message;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.innerText = text ?? "";
  return div.innerHTML;
}

function renderSources(references = []) {
  if (!references.length) {
    sourcesEl.innerHTML = "No sources returned.";
    return;
  }

  sourcesEl.innerHTML = references.map((ref, idx) => {
    const title = escapeHtml(ref.title || `Source ${idx + 1}`);
    const uri = ref.link || ref.uri || "";
    const snippet =
      ref.extractive_answers?.[0]?.content ||
      ref.extractive_segments?.[0]?.content ||
      ref.snippets?.[0]?.snippet ||
      "";

    return `
      <div class="source-item">
        <strong>${title}</strong><br/>
        ${uri ? `<a href="${uri}" target="_blank">${escapeHtml(uri)}</a><br/>` : ""}
        ${snippet ? `<div><em>Relevant text:</em> ${snippet}</div>` : ""}
      </div>
    `;
  }).join("");
}

function renderResults(results = []) {
  if (!results.length) {
    resultsEl.innerHTML = "No search results returned.";
    return;
  }

  resultsEl.innerHTML = results.map((item, idx) => {
    const title = escapeHtml(item.title || `Result ${idx + 1}`);
    const link = item.link || "";
    const snippet = item.snippets?.[0]?.snippet || "";
    const extractive = item.extractive_answers?.[0]?.content || item.extractive_segments?.[0]?.content || "";

    return `
      <div class="result-item">
        <strong>${title}</strong><br/>
        ${link ? `<a href="${link}" target="_blank">${escapeHtml(link)}</a><br/>` : ""}
        ${snippet ? `<div><em>Snippet:</em> ${snippet}</div>` : ""}
        ${extractive ? `<div><em>Extractive:</em> ${extractive}</div>` : ""}
      </div>
    `;
  }).join("");
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

askBtn.addEventListener("click", async () => {
  const question = questionEl.value.trim();
  if (!question) return;

  setLoading(true, "Generating grounded answer...");
  answerEl.textContent = "Loading...";
  sourcesEl.textContent = "Loading...";

  try {
    const data = await postJson("/api/ask", { question, user_pseudo_id: "browser-user-1" });
    answerEl.textContent = data.answer || "No answer returned.";
    renderSources(data.references || []);
    statusEl.textContent = "Answer ready.";
  } catch (err) {
    answerEl.textContent = `Error: ${err.message}`;
    sourcesEl.textContent = "No sources.";
    statusEl.textContent = "Answer failed.";
  } finally {
    setLoading(false, statusEl.textContent);
  }
});

searchBtn.addEventListener("click", async () => {
  const question = questionEl.value.trim();
  if (!question) return;

  setLoading(true, "Searching documents...");
  resultsEl.textContent = "Loading...";

  try {
    const data = await postJson("/api/search", { question, user_pseudo_id: "browser-user-1" });
    renderResults(data.results || []);
    statusEl.textContent = "Search complete.";
  } catch (err) {
    resultsEl.textContent = `Error: ${err.message}`;
    statusEl.textContent = "Search failed.";
  } finally {
    setLoading(false, statusEl.textContent);
  }
});