(() => {
  const $ = (s) => document.querySelector(s);
  const data = JSON.parse($("#payload").textContent);

  const note = sessionStorage.getItem("triageNote");
  if (note) {
  $("#note").textContent = note;
  $("#note").hidden = false;
  sessionStorage.removeItem("triageNote");
  }

  // ---- run triage (also available on the empty state) ----
  const runBtns = document.querySelectorAll(".js-run");
  runBtns.forEach((btn) =>
    btn.addEventListener("click", async () => {
      $("#error").hidden = true;
      $("#busy").hidden = false;
      runBtns.forEach((b) => {
        b.dataset.label = b.textContent;
        b.disabled = true;
        b.innerHTML = '<span class="spinner"></span>Triaging…';
      });

      const poll = setInterval(async () => {
      try {
        const s = await (await fetch("/api/triage/status")).json();
        if (s.message) $("#busy").textContent = s.message;
      } catch (_) {}
    }, 1500);
    try {
      const res = await fetch("/api/triage", { method: "POST" });
      if (!res.ok) {
        let msg;
        try { msg = (await res.json()).detail; } catch (_) {}
        throw new Error(msg || `Request failed (${res.status})`);
      }
      const s = await (await fetch("/api/triage/status")).json();
      if (s.fallback) sessionStorage.setItem("triageNote", "These results were generated with a fallback model because the main model reached its daily usage limit.");
      location.reload();
    } catch (err) {
      $("#error").textContent = err.message;
      $("#error").hidden = false;
      $("#busy").hidden = true;
      runBtns.forEach((b) => { b.disabled = false; b.textContent = b.dataset.label; });
    } finally {
      clearInterval(poll);
    }
    })
  );

  if (!data.tickets.length) return;

  // ---- list, filters, sorting ----
  const listEl = $("#list");
  const byId = new Map(data.tickets.map((t) => [t.id, t]));
  const rows = new Map([...listEl.querySelectorAll(".row")].map((r) => [Number(r.dataset.id), r]));
  const f = { q: "", urgency: "", category: "", sentiment: "", sort: "urgency" };
  const edits = {};
  let selected = null;
  let visible = [];

  const rank = (key, v) => { const i = data.ranks[key].indexOf(v); return i < 0 ? 99 : i; };

  function apply() {
    visible = data.tickets.filter((t) =>
      (!f.urgency || t.urgency === f.urgency) &&
      (!f.category || t.category === f.category) &&
      (!f.sentiment || t.sentiment === f.sentiment) &&
      (!f.q || t.message.toLowerCase().includes(f.q))
    );
    visible.sort((a, b) => {
      if (f.sort === "urgency") return rank("urgency", a.urgency) - rank("urgency", b.urgency) || a.id - b.id;
      if (f.sort === "sentiment") return rank("sentiment", a.sentiment) - rank("sentiment", b.sentiment) || a.id - b.id;
      if (f.sort === "category") return a.category.localeCompare(b.category) || a.id - b.id;
      return a.id - b.id;
    });
    rows.forEach((r) => (r.hidden = true));
    visible.forEach((t) => { const r = rows.get(t.id); r.hidden = false; listEl.appendChild(r); });
    $("#count").textContent = `(${visible.length} of ${data.tickets.length})`;
    $("#none").hidden = visible.length > 0;
    if (!visible.some((t) => t.id === selected)) select(visible.length ? visible[0].id : null);
  }

  function select(id, scroll) {
    selected = id;
    rows.forEach((r, rid) => {
      r.classList.toggle("active", rid === id);
      r.setAttribute("aria-pressed", String(rid === id));
    });
    $("#detail").hidden = id === null;
    if (id === null) return;
    const t = byId.get(id);
    $("#d-title").textContent = `Ticket #${t.id}`;
    $("#d-urg").className = `pill urg-${t.urgency.toLowerCase()}`;
    $("#d-urg").textContent = t.urgency;
    $("#d-sen").className = `pill sen-${t.sentiment.toLowerCase()}`;
    $("#d-sen").textContent = t.sentiment;
    $("#d-cat").textContent = t.category;
    $("#d-msg").textContent = t.message;
    $("#d-reply").value = edits[id] ?? t.suggested_reply;
    $("#d-status").textContent = "";
    if (scroll && window.innerWidth < 1000) $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  listEl.addEventListener("click", (e) => {
    const r = e.target.closest(".row");
    if (r) select(Number(r.dataset.id), true);
  });

  const bind = (id, key, ev = "change") =>
    $(id).addEventListener(ev, (e) => { f[key] = key === "q" ? e.target.value.trim().toLowerCase() : e.target.value; apply(); });
  bind("#f-q", "q", "input");
  bind("#f-urgency", "urgency");
  bind("#f-category", "category");
  bind("#f-sentiment", "sentiment");
  bind("#f-sort", "sort");

  $("#clear").addEventListener("click", () => {
    Object.assign(f, { q: "", urgency: "", category: "", sentiment: "", sort: "urgency" });
    $("#f-q").value = "";
    ["urgency", "category", "sentiment"].forEach((k) => ($("#f-" + k).value = ""));
    $("#f-sort").value = "urgency";
    apply();
  });

  // ---- reply editing ----
  $("#d-reply").addEventListener("input", (e) => { edits[selected] = e.target.value; });
  $("#d-reset").addEventListener("click", () => {
    delete edits[selected];
    $("#d-reply").value = byId.get(selected).suggested_reply;
    $("#d-status").textContent = "Reset to the AI draft";
  });
  $("#d-copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#d-reply").value);
      $("#d-status").textContent = "Copied to clipboard";
    } catch (_) {
      $("#d-reply").select();
      $("#d-status").textContent = "Press Ctrl+C to copy";
    }
  });

  // ---- CSV export of the current view ----
  $("#export").addEventListener("click", () => {
    const esc = (v) => `"${String(v).replaceAll('"', '""')}"`;
    const head = ["ID", "Message", "Urgency", "Category", "Sentiment", "Suggested reply"];
    const lines = visible.map((t) => [t.id, t.message, t.urgency, t.category, t.sentiment, edits[t.id] ?? t.suggested_reply].map(esc).join(","));
    const blob = new Blob([[head.map(esc).join(","), ...lines].join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "triaged_tickets.csv" });
    a.click();
    URL.revokeObjectURL(a.href);
  });

  apply();
})();
