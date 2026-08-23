const AVATAR_COLORS = ["#534AB7","#0F6E56","#993C1D","#185FA5","#854F0B","#993556","#3B6D11"];
const FALLBACK_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300";

function avatarColor(name){
  let h=0; for(const c of name) h=(h*31+c.charCodeAt(0))&0xffffffff;
  return AVATAR_COLORS[Math.abs(h)%AVATAR_COLORS.length];
}

function piconHTML(name, size=22){
  const p = window.PLATFORMS?.[name] || {bg:"#888", fg:"#fff", label: name.slice(0,2).toUpperCase()};
  const el = document.createElement("div");
  el.className = "picon";
  el.style.width = size + "px";
  el.style.height = size + "px";
  el.title = name;
  if(p.logo){
    // Brand mark: recolor the SVG via CSS mask
    el.style.background = p.bg;
    el.style.webkitMask = `url(${p.logo}) center / contain no-repeat`;
    el.style.mask = `url(${p.logo}) center / contain no-repeat`;
  }else{
    el.style.background = p.bg;
    el.style.color = p.fg;
    el.textContent = p.label;
  }
  return el;
}

function starsHTML(avg){
  let s = "";
  for(let i=1;i<=5;i++){
    if(avg >= i-0.25)      s += `<span class="star">★</span>`;
    else if(avg >= i-0.75) s += `<span class="star">½</span>`;
    else                   s += `<span class="star empty">★</span>`;
  }
  return s;
}

// Fill a "label value" line; hide the whole line when the value is empty.
function fillLine(lineId, valueId, value){
  const v = (value || "").toString().trim();
  document.getElementById(valueId).textContent = v;
  document.getElementById(lineId).style.display = v ? "" : "none";
}

// ---------------------------------------------------------------- //
// Entries data — fetched once from the API, then cached             //
// ---------------------------------------------------------------- //
let ENTRIES = null;
async function loadEntries(){
  if(!ENTRIES){
    const resp = await fetch("/api/entries");
    ENTRIES = await resp.json();
  }
  return ENTRIES;
}

async function openModal(title){
  const entries = await loadEntries();
  const item = entries.find(e => e.title === title);
  if(!item) return;

  const avg = item.ratings.length
    ? item.ratings.reduce((a,r) => a+r.score, 0) / item.ratings.length
    : null;

  document.getElementById("modal-poster").src = item.poster || FALLBACK_POSTER;
  document.getElementById("modal-title").textContent = item.title;
  document.getElementById("modal-score").textContent = avg !== null ? avg.toFixed(1) : "—";
  document.getElementById("modal-stars").innerHTML   = avg !== null ? starsHTML(avg) : "";
  document.getElementById("modal-count").textContent = item.ratings.length
    ? `${item.ratings.length} rating${item.ratings.length !== 1 ? "s" : ""}`
    : "No ratings yet";

  const genresEl = document.getElementById("modal-genres");
  genresEl.innerHTML = "";
  for(const g of item.genres){
    const t = document.createElement("span");
    t.className = "gtag";
    t.textContent = g;
    genresEl.appendChild(t);
  }

  const platEl = document.getElementById("modal-platforms");
  platEl.innerHTML = "";
  if(!item.platforms.length){
    const none = document.createElement("span");
    none.className = "no-platforms";
    none.textContent = "Not currently streaming";
    platEl.appendChild(none);
  } else {
    for(const p of item.platforms){
      const pill = document.createElement("div");
      pill.className = "stream-pill";
      pill.appendChild(piconHTML(p, 20));
      const nm = document.createElement("span");
      nm.textContent = p;
      pill.appendChild(nm);
      platEl.appendChild(pill);
    }
  }

  fillLine("modal-director-line", "modal-director", item.director);
  fillLine("modal-actors-line", "modal-actors", (item.actors || []).join(", "));

  const plotEl = document.getElementById("modal-plot");
  plotEl.textContent = item.plot || "";
  plotEl.style.display = item.plot ? "" : "none";

  // Build 5→1 bar rows
  const byScore = {5:[],4:[],3:[],2:[],1:[]};
  for(const r of item.ratings){
    const b = Math.round(r.score);
    if(byScore[b]) byScore[b].push(r);
  }

  const barsEl = document.getElementById("modal-bars");
  if(!item.ratings.length){
    barsEl.innerHTML = `<p class="no-ratings">No ratings yet — use /rate ${item.title} - 4.5</p>`;
  } else {
    barsEl.innerHTML = "";
    for(let s=5; s>=1; s--){
      const reviewers = byScore[s] || [];
      const pct = Math.round((reviewers.length / item.ratings.length) * 100);

      const row = document.createElement("div");
      row.className = "bar-row";

      const label = document.createElement("div");
      label.className = "bar-label";
      label.textContent = s;

      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = pct + "%";
      track.appendChild(fill);

      const avatars = document.createElement("div");
      avatars.className = "bar-avatars";
      for(const r of reviewers){
        const a = document.createElement("div");
        a.className = "bar-avatar";
        a.style.background = avatarColor(r.user);
        a.style.color = "#fff";
        a.title = `${r.user} — ${r.score}/5`;
        a.textContent = r.user[0].toUpperCase();
        avatars.appendChild(a);
      }

      row.append(label, track, avatars);
      barsEl.appendChild(row);
    }
  }

  document.getElementById("modal-overlay").classList.add("open");
}

function closeModal(){
  document.getElementById("modal-overlay").classList.remove("open");
}

// ---------------------------------------------------------------- //
// Event delegation — no inline onclick handlers                     //
// ---------------------------------------------------------------- //
document.addEventListener("click", (e) => {
  const card = e.target.closest(".card");
  if(card && card.dataset.title){ openModal(card.dataset.title); return; }

  const nav = e.target.closest("[data-page]");
  if(nav){ showPage(nav.dataset.page); return; }

  const btn = e.target.closest(".gfbtn");
  if(btn){ filterGenre(btn); return; }

  if(e.target.id === "modal-overlay" || e.target.closest(".modal-close")) closeModal();
});

document.addEventListener("keydown", e => {
  if(e.key === "Escape") closeModal();
});

function showPage(id){
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  window.scrollTo(0, 0);
}

function filterGenre(btn){
  // Multi-select: toggle tags per page; cards match ANY selected tag.
  const page = btn.closest(".page");
  if(page._genreSel === undefined) page._genreSel = new Set();
  const sel = page._genreSel;
  const genre = btn.dataset.genre;

  if(genre === "all"){
    sel.clear();
  } else {
    sel.has(genre) ? sel.delete(genre) : sel.add(genre);
  }

  page.querySelectorAll(".gfbtn").forEach(b => {
    b.classList.toggle("active",
      b.dataset.genre === "all" ? sel.size === 0 : sel.has(b.dataset.genre));
  });

  page.querySelectorAll(".full-grid .card").forEach(card => {
    if(sel.size === 0){ card.classList.remove("hidden"); return; }
    const genres = JSON.parse(card.dataset.genres || "[]");
    card.classList.toggle("hidden", !genres.some(g => sel.has(g)));
  });
}
