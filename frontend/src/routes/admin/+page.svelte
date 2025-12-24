
<script>
  export let data;

  // Portfolios fetched from your load()
  let portfolios = data?.props?.portfolios ?? [];

  // Search + sort + selection
  let query = "";
  let sortKey = "name";   // "name" | "start_date" | "end_date" | "manager_name"
  let sortDir = "asc";    // "asc" | "desc"

  let selectedId = null;

  // Helpers
  const safe = (v) => (v ?? "").toString();
  const toLower = (v) => safe(v).toLowerCase();

  const fmtDate = (d) => {
    if (!d) return "—";
    // supports "YYYY-MM-DD" or Date-ish strings
    try {
      const dt = new Date(d);
      if (Number.isNaN(dt.getTime())) return safe(d);
      return dt.toISOString().slice(0, 10);
    } catch {
      return safe(d);
    }
  };

  const isActive = (p) => !p?.end_date;

  // Reactive filtering
  $: q = query.trim().toLowerCase();
  $: filtered =
    q === ""
      ? portfolios
      : portfolios.filter((p) => {
          const id = safe(p?.id);
          const name = toLower(p?.name);
          const manager = toLower(p?.manager_name);
          const desc = toLower(p?.description);
          const start = toLower(p?.start_date);
          const end = toLower(p?.end_date);
          return (
            id.includes(q) ||
            name.includes(q) ||
            manager.includes(q) ||
            desc.includes(q) ||
            start.includes(q) ||
            end.includes(q)
          );
        });

  // Reactive sorting
  const cmp = (a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;

    const av = a?.[sortKey];
    const bv = b?.[sortKey];

    // dates: compare as date if possible
    const isDateKey = sortKey === "start_date" || sortKey === "end_date";
    if (isDateKey) {
      const ad = av ? new Date(av).getTime() : -Infinity; // null end_date => very small (shows first in asc)
      const bd = bv ? new Date(bv).getTime() : -Infinity;
      return (ad - bd) * dir;
    }

    // numbers (id)
    if (sortKey === "id") {
      return ((Number(av) || 0) - (Number(bv) || 0)) * dir;
    }

    // strings
    return safe(av).localeCompare(safe(bv), undefined, { sensitivity: "base" }) * dir;
  };

  $: sorted = [...filtered].sort(cmp);

  // Selection
  $: selected = selectedId == null ? null : sorted.find((p) => p?.id === selectedId) ?? null;

  function toggleSort(key) {
    if (sortKey === key) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = "asc";
    }
  }

  function selectRow(p) {
    selectedId = p?.id;
  }
</script>

<div class="page">
  <div class="card">
    <div class="header">
      <div class="headerTop">
        <div>
          <h1 class="title">PORTFOLIO TERMINAL</h1>
          <div class="subtitle">{sorted.length} portfolio(s) shown</div>
        </div>

        <div class="meta">
          <span class="chip">{sortKey} · {sortDir}</span>
          <span class="chip">{selected ? `Selected #${selected.id}` : "No selection"}</span>

          <a class="btnSmall" href="/portfolios/new">+ NEW</a>
        </div>
      </div>

      <div class="controls">
        <div class="searchWrap">
          <input
            type="text"
            class="searchInput"
            placeholder="Search id, name, manager, dates, description…"
            bind:value={query}
          />
        </div>

        <div class="hint">
          Click a row to see details · Click headers to sort
        </div>
      </div>

      <div class="scanline" aria-hidden="true"></div>
    </div>

    <div class="body">
      <div class="tableWrap">
        <table class="kittTable">
          <thead>
            <tr>
              <th class="clickable" on:click={() => toggleSort("id")}>
                ID <span class="arrow">{sortKey === "id" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
              </th>
              <th class="clickable" on:click={() => toggleSort("name")}>
                Name <span class="arrow">{sortKey === "name" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
              </th>
              <th class="clickable" on:click={() => toggleSort("start_date")}>
                Start <span class="arrow">{sortKey === "start_date" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
              </th>
              <th class="clickable" on:click={() => toggleSort("end_date")}>
                End <span class="arrow">{sortKey === "end_date" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
              </th>
              <th class="clickable" on:click={() => toggleSort("manager_name")}>
                Manager <span class="arrow">{sortKey === "manager_name" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
              </th>
              <th>Status</th>
            </tr>
          </thead>

          <tbody>
            {#if sorted.length === 0}
              <tr>
                <td class="empty" colspan="6">No portfolios found</td>
              </tr>
            {:else}
              {#each sorted as p (p.id)}
                <tr
                  class:selected={selectedId === p.id}
                  on:click={() => selectRow(p)}
                  tabindex="0"
                  on:keydown={(e) => e.key === "Enter" && selectRow(p)}
                >
                  <td><span class="mono">#{p.id}</span></td>
                  <td class="nameCell">
                    <span class="name">{p.name}</span>
                    {#if p.description}
                      <span class="desc">{p.description}</span>
                    {/if}
                  </td>
                  <td><span class="mono">{fmtDate(p.start_date)}</span></td>
                  <td><span class="mono">{fmtDate(p.end_date)}</span></td>
                  <td>{p.manager_name ?? "—"}</td>
                  <td>
                    {#if isActive(p)}
                      <span class="badge active">ACTIVE</span>
                    {:else}
                      <span class="badge closed">CLOSED</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>

      <!-- Details panel -->
      <aside class="details">
        <div class="detailsHeader">
          <div class="detailsTitle">DETAILS</div>
          <div class="detailsSub">{selected ? `Portfolio #${selected.id}` : "Select a row"}</div>
        </div>

        {#if !selected}
          <div class="detailsEmpty">
            No portfolio selected.
            <div class="detailsEmptyHint">Tip: click a row to inspect manager, dates, description.</div>
          </div>
        {:else}
          <div class="detailsGrid">
            <div class="kv">
              <div class="k">Name</div>
              <div class="v">{selected.name}</div>
            </div>

            <div class="kv">
              <div class="k">Manager</div>
              <div class="v">{selected.manager_name ?? "—"}</div>
            </div>

            <div class="kv">
              <div class="k">Start date</div>
              <div class="v mono">{fmtDate(selected.start_date)}</div>
            </div>

            <div class="kv">
              <div class="k">End date</div>
              <div class="v mono">{fmtDate(selected.end_date)}</div>
            </div>

            <div class="kv full">
              <div class="k">Description</div>
              <div class="v">{selected.description ?? "—"}</div>
            </div>

            <div class="kv full">
              <div class="k">Positions</div>
              <div class="v">
                <span class="muted">
                  positions: {Array.isArray(selected.positions) ? selected.positions.length : "—"}
                </span>
                <div class="muted small">
                  (Tu peux brancher un “View positions” qui navigue vers /portfolios/{selected.id})
                </div>
              </div>
            </div>
          </div>

          <div class="actions">
            <!-- Remplace href selon ton routing -->
            <a class="btn" href={`/portfolios/${selected.id}`}>Open</a>
            <a class="btn ghost" href={`/portfolios/${selected.id}/positions`}>Positions</a>
          </div>
        {/if}
      </aside>
    </div>
  </div>
</div>

<style>
  .page {
    min-height: calc(100vh - 80px);
    padding: 96px 20px 40px;
    padding-top: 12vh;
    display: flex;
    align-items: center;
    justify-content: center;

    background:
      radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
      linear-gradient(180deg, #07080c, #04040a);
  }

  .card {
    width: min(1200px, 100%);
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
    border: 1px solid rgba(255, 0, 60, 0.22);
    box-shadow:
      0 0 0 1px rgba(255, 0, 60, 0.08),
      0 20px 60px rgba(0, 0, 0, 0.65),
      0 0 30px rgba(255, 0, 60, 0.08);
    overflow: hidden;
    position: relative;
  }

  .header {
    position: relative;
    padding: 18px 20px 16px;
    border-bottom: 1px solid rgba(255, 0, 60, 0.16);
    background:
      linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
      linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
  }

  .headerTop {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
  }

  .title {
    margin: 0;
    font-size: 14px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: rgba(255, 0, 60, 0.95);
    text-shadow: 0 0 12px rgba(255, 0, 60, 0.35);
  }

  .subtitle {
    margin-top: 6px;
    font-size: 12px;
    color: rgba(235, 235, 245, 0.65);
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: flex-end;
  }

  .chip {
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.75);
    border: 1px solid rgba(255, 0, 60, 0.22);
    background: rgba(255, 0, 60, 0.08);
    padding: 6px 10px;
    border-radius: 999px;
  }

  .controls {
    margin-top: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .searchWrap { max-width: 420px; flex: 1; min-width: 260px; }

  .searchInput {
    width: 100%;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.9);
    background:
      linear-gradient(180deg, rgba(255, 0, 60, 0.10), rgba(255, 0, 60, 0.02));
    border: 1px solid rgba(255, 0, 60, 0.28);
    outline: none;
    box-shadow:
      inset 0 0 12px rgba(255, 0, 60, 0.12),
      0 0 14px rgba(255, 0, 60, 0.08);
    transition: border 150ms ease, box-shadow 150ms ease;
  }

  .searchInput::placeholder {
    color: rgba(235, 235, 245, 0.45);
    letter-spacing: 0.04em;
  }

  .searchInput:focus {
    border-color: rgba(255, 0, 60, 0.55);
    box-shadow:
      inset 0 0 14px rgba(255, 0, 60, 0.18),
      0 0 20px rgba(255, 0, 60, 0.25);
  }

  .hint {
    font-size: 12px;
    color: rgba(235, 235, 245, 0.55);
    letter-spacing: 0.02em;
  }

  .scanline {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(180deg, transparent, rgba(255, 0, 60, 0.08), transparent);
    height: 120px;
    transform: translateY(-120px);
    animation: scan 4.5s linear infinite;
    opacity: 0.75;
  }

  @keyframes scan {
    0% { transform: translateY(-120px); }
    100% { transform: translateY(320px); }
  }

  .body {
    display: grid;
    grid-template-columns: 1.35fr 0.65fr;
    gap: 14px;
    padding: 14px;
  }

  @media (max-width: 980px) {
    .body { grid-template-columns: 1fr; }
  }

  .tableWrap {
    max-height: 65vh;
    overflow: auto;
    padding: 2px;
  }

  .kittTable {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 0, 60, 0.18);
    border-radius: 14px;
    overflow: hidden;
  }

  .kittTable thead th {
    text-align: left;
    font-size: 12px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.85);
    background:
      linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
    padding: 14px 14px;
    border-bottom: 1px solid rgba(255, 0, 60, 0.16);
    position: sticky;
    top: 0;
    z-index: 1;
    user-select: none;
    white-space: nowrap;
  }

  .clickable { cursor: pointer; }
  .arrow { margin-left: 6px; opacity: 0.8; }

  .kittTable tbody td {
    padding: 12px 14px;
    font-size: 14px;
    color: rgba(235, 235, 245, 0.85);
    border-bottom: 1px solid rgba(255, 0, 60, 0.10);
    vertical-align: top;
  }

  .kittTable tbody tr {
    transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
    cursor: pointer;
  }

  .kittTable tbody tr:hover {
    background: rgba(255, 0, 60, 0.07);
    box-shadow: inset 0 0 0 1px rgba(255, 0, 60, 0.20);
  }

  .kittTable tbody tr.selected {
    background: rgba(255, 0, 60, 0.10);
    box-shadow:
      inset 0 0 0 1px rgba(255, 0, 60, 0.35),
      inset 0 0 18px rgba(255, 0, 60, 0.10);
  }

  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    letter-spacing: 0.02em;
    color: rgba(255, 210, 220, 0.95);
    text-shadow: 0 0 10px rgba(255, 0, 60, 0.18);
    white-space: nowrap;
  }

  .nameCell .name { display: block; font-weight: 600; }
  .nameCell .desc {
    display: block;
    margin-top: 4px;
    font-size: 12px;
    color: rgba(235, 235, 245, 0.55);
    line-height: 1.35;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid rgba(255, 0, 60, 0.22);
    box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    white-space: nowrap;
  }
  .badge.active {
    color: rgba(255, 255, 255, 0.88);
    background: rgba(255, 0, 60, 0.10);
  }
  .badge.closed {
    color: rgba(255, 255, 255, 0.75);
    background: rgba(255, 0, 60, 0.06);
    opacity: 0.9;
  }

  .empty {
    text-align: center;
    padding: 22px 14px !important;
    color: rgba(235, 235, 245, 0.55) !important;
  }

  /* Details panel */
  .details {
    border-radius: 14px;
    border: 1px solid rgba(255, 0, 60, 0.18);
    background: rgba(0, 0, 0, 0.22);
    overflow: hidden;
    min-height: 320px;
    display: flex;
    flex-direction: column;
  }

  .detailsHeader {
    padding: 14px 14px 12px;
    border-bottom: 1px solid rgba(255, 0, 60, 0.14);
    background:
      linear-gradient(90deg, rgba(255, 0, 60, 0.08), transparent 65%),
      linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
  }

  .detailsTitle {
    font-size: 12px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: rgba(255, 0, 60, 0.95);
    text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
  }

  .detailsSub {
    margin-top: 6px;
    font-size: 12px;
    color: rgba(235, 235, 245, 0.62);
  }

  .detailsEmpty {
    padding: 16px 14px;
    color: rgba(235, 235, 245, 0.7);
  }

  .detailsEmptyHint {
    margin-top: 8px;
    font-size: 12px;
    color: rgba(235, 235, 245, 0.55);
  }

  .detailsGrid {
    padding: 14px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .kv {
    border: 1px solid rgba(255, 0, 60, 0.14);
    background: rgba(255, 0, 60, 0.05);
    border-radius: 12px;
    padding: 10px 10px;
  }

  .kv.full { grid-column: 1 / -1; }

  .k {
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(235, 235, 245, 0.58);
    margin-bottom: 6px;
  }

  .v {
    font-size: 14px;
    color: rgba(235, 235, 245, 0.88);
    line-height: 1.35;
    word-break: break-word;
  }

  .muted { color: rgba(235, 235, 245, 0.62); }
  .small { font-size: 12px; }

  .actions {
    margin-top: auto;
    padding: 12px 14px 14px;
    display: flex;
    gap: 10px;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 0, 60, 0.28);
    background: rgba(255, 0, 60, 0.10);
    color: rgba(255, 255, 255, 0.9);
    text-decoration: none;
    font-size: 13px;
    letter-spacing: 0.04em;
    box-shadow:
      inset 0 0 12px rgba(255, 0, 60, 0.10),
      0 0 16px rgba(255, 0, 60, 0.10);
    transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
  }

  .btn:hover {
    transform: translateY(-1px);
    border-color: rgba(255, 0, 60, 0.55);
    box-shadow:
      inset 0 0 14px rgba(255, 0, 60, 0.16),
      0 0 20px rgba(255, 0, 60, 0.22);
  }

  .btn.ghost {
    background: rgba(255, 0, 60, 0.06);
    border-color: rgba(255, 0, 60, 0.18);
    color: rgba(255, 255, 255, 0.82);
  }

  .btnSmall {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 0, 60, 0.28);
  background: rgba(255, 0, 60, 0.10);
  color: rgba(255, 255, 255, 0.9);
  font-size: 11px;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  text-decoration: none;
  cursor: pointer;
  box-shadow:
    inset 0 0 12px rgba(255, 0, 60, 0.10),
    0 0 16px rgba(255, 0, 60, 0.10);
  transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
}

.btnSmall:hover {
  transform: translateY(-1px);
  border-color: rgba(255, 0, 60, 0.55);
  box-shadow:
    inset 0 0 14px rgba(255, 0, 60, 0.16),
    0 0 20px rgba(255, 0, 60, 0.22);
}

  /* Thin red scrollbar */
  .tableWrap::-webkit-scrollbar { height: 10px; width: 10px; }
  .tableWrap::-webkit-scrollbar-thumb {
    background: rgba(255, 0, 60, 0.25);
    border-radius: 999px;
    border: 2px solid rgba(0, 0, 0, 0.35);
  }
  .tableWrap::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.25); }
</style>
