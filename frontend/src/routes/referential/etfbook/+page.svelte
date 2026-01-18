<script>
    import {onMount} from "svelte";
    import {goto} from "$app/navigation";

    let limit = 200;
    let offset = 0;

    let loading = false;
    let err = null;
    let page = null;

    // 🔎 Search (SERVER-SIDE)
    let q = "";

    // debounce timer
    let t = null;

    // Colonnes préférées (ajuste si besoin)
    const preferredCols = ["fundISIN", "fundName", "fundBrand", "exchangeReutersCode", "exchangeName", "exchangeBloombergCode",
        "exchangeListingDate", "fundCurrency", "fundType", "fundAssetClass", "fundAssetSubClass", "fundAssetClassGeoFocus",
        "fundInceptionDate", "fundReplicationType", "fundTER", "fundSFDR", "fundTaxReportingFRPEA"];

    async function loadPage() {
        loading = true;
        err = null;

        try {
            const params = new URLSearchParams({
                limit: String(limit),
                offset: String(offset)
            });

            if (q.trim()) {
                params.set("q", q.trim());
            }

            const res = await fetch(
                `http://localhost:8000/referential/etfbook/static-data?${params.toString()}`
            );

            const ct = res.headers.get("content-type") ?? "";
            if (!res.ok) {
                const text = await res.text();
                throw new Error(text || `HTTP ${res.status}`);
            }
            if (!ct.includes("application/json")) {
                const text = await res.text();
                throw new Error(`Expected JSON, got ${ct}\n\n${text.slice(0, 400)}`);
            }

            page = await res.json();
        } catch (e) {
            err = e?.message ?? "Unknown error";
            page = null;
        } finally {
            loading = false;
        }
    }

    function onSearchInput() {
        offset = 0; // reset pagination on search
        clearTimeout(t);
        t = setTimeout(() => {
            loadPage();
        }, 300);
    }

    function next() {
        if (!page) return;
        const nextOffset = offset + limit;
        if (nextOffset >= page.total) return;
        offset = nextOffset;
        loadPage();
    }

    function prev() {
        const prevOffset = Math.max(0, offset - limit);
        if (prevOffset === offset) return;
        offset = prevOffset;
        loadPage();
    }

    function getValue(row, col) {
        if (!row || !col) return "";

        // 1) match exact
        if (row[col] !== undefined) {
            return row[col];
        }

        // 2) match case-insensitive
        const key = Object.keys(row).find(
            (k) => k.toLowerCase() === col.toLowerCase()
        );

        return key ? row[key] : "";
    }

    const cols = preferredCols;

    onMount(loadPage);
</script>

<style>
    /* --- K2000 / KITT Skin (ton CSS) --- */
    /* Page */
    .page {
        min-height: calc(90vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        background: radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
        linear-gradient(180deg, #07080c, #04040a);
    }

    /* Card */
    .card {
        width: min(1200px, 100%);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow: 0 0 0 1px rgba(255, 0, 60, 0.08), 0 20px 60px rgba(0, 0, 0, 0.65),
        0 0 30px rgba(255, 0, 60, 0.08);
        overflow: hidden;
        position: relative;
    }

    /* Header */
    .header {
        position: relative;
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background: linear-gradient(90deg, rgba(255, 0, 60, 0.1), transparent 60%),
        linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }

    .headerGrid {
        display: grid;
        grid-template-columns: 1fr 320px;
        gap: 16px;
        align-items: start;
    }

    @media (max-width: 900px) {
        .headerGrid {
            grid-template-columns: 1fr;
        }
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

    /* Search */
    .searchWrap {
        margin-top: 12px;
        max-width: 420px;
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
    }

    .searchInput {
        width: 100%;
        padding: 10px 14px;
        border-radius: 10px;
        font-size: 13px;
        color: rgba(255, 255, 255, 0.9);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.1), rgba(255, 0, 60, 0.02));
        border: 1px solid rgba(255, 0, 60, 0.28);
        outline: none;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.12), 0 0 14px rgba(255, 0, 60, 0.08);
        transition: border 150ms ease, box-shadow 150ms ease;
    }

    .searchInput::placeholder {
        color: rgba(235, 235, 245, 0.45);
        letter-spacing: 0.04em;
    }

    .searchInput:focus {
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.18), 0 0 20px rgba(255, 0, 60, 0.25);
    }

    /* Controls */
    .controls {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        align-items: center;
        flex-wrap: wrap;
    }

    .label {
        font-size: 12px;
        color: rgba(235, 235, 245, 0.65);
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .limitInput {
        width: 110px;
        padding: 10px 12px;
        border-radius: 10px;
        font-size: 13px;
        color: rgba(255, 255, 255, 0.9);
        background: rgba(0, 0, 0, 0.25);
        border: 1px solid rgba(255, 0, 60, 0.28);
        outline: none;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.08);
    }

    .btn {
        padding: 10px 14px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.14), rgba(0, 0, 0, 0.25));
        color: rgba(255, 255, 255, 0.88);
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        cursor: pointer;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.1), 0 0 18px rgba(255, 0, 60, 0.06);
        transition: transform 120ms ease, border 120ms ease, box-shadow 120ms ease;
    }

    .btn:hover:not(:disabled) {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 22px rgba(255, 0, 60, 0.1);
    }

    .btn:disabled {
        opacity: 0.45;
        cursor: not-allowed;
    }

    .pill {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: rgba(255, 0, 60, 0.1);
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .err {
        margin-top: 10px;
        font-size: 12px;
        color: rgba(255, 160, 160, 0.95);
        white-space: pre-wrap;
    }

    .ok {
        margin-top: 10px;
        font-size: 12px;
        color: rgba(180, 255, 200, 0.95);
    }

    /* Scanline */
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

    .kittTable tbody tr {
        cursor: pointer;
    }

    .kittTable tbody tr:active {
        transform: scale(0.995);
    }

    @keyframes scan {
        0% {
            transform: translateY(-120px);
        }
        100% {
            transform: translateY(260px);
        }
    }

    /* Table */
    .tableWrap {
        padding: 14px;
        max-height: 60vh;
        overflow-y: auto;
        overflow-x: auto;
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
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
        padding: 14px 14px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .kittTable tbody td {
        padding: 12px 14px;
        font-size: 14px;
        color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.1);
        white-space: nowrap;
    }

    .kittTable tbody tr {
        transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
    }

    .kittTable tbody tr:hover {
        background: rgba(255, 0, 60, 0.07);
        box-shadow: inset 0 0 0 1px rgba(255, 0, 60, 0.2);
    }

    .kittTable tbody tr:hover td {
        color: rgba(255, 255, 255, 0.92);
    }

    .empty {
        text-align: center;
        padding: 22px 14px !important;
        color: rgba(235, 235, 245, 0.55) !important;
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
        "Courier New", monospace;
        letter-spacing: 0.02em;
        color: rgba(255, 210, 220, 0.95);
        text-shadow: 0 0 10px rgba(255, 0, 60, 0.18);
    }

    .tableWrap::-webkit-scrollbar {
        height: 10px;
        width: 10px;
    }

    .tableWrap::-webkit-scrollbar-thumb {
        background: rgba(255, 0, 60, 0.25);
        border-radius: 999px;
        border: 2px solid rgba(0, 0, 0, 0.35);
    }

    .tableWrap::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.25);
    }
</style>

<div class="page">
    <section class="card">
        <div class="scanline"></div>

        <header class="header">
            <div class="headerGrid">
                <div>
                    <h2 class="title">ETFBOOK • STATIC DATA</h2>
                    <div class="subtitle">
                        Server-side search across all rows. Pagination is applied after filtering.
                    </div>

                    <div class="searchWrap">
                        <input
                                class="searchInput"
                                placeholder="Search (ISIN, Symbol, Name, PEA, etc...)"
                                bind:value={q}
                                on:input={onSearchInput}
                        />

                        {#if page}
                            <span class="pill">{page.count} results</span>
                            <span class="pill">{page.total} total</span>
                        {/if}
                    </div>

                    {#if err}
                        <div class="err">{err}</div>
                    {/if}

                    {#if loading}
                        <div class="ok">Loading…</div>
                    {/if}
                </div>

                <div class="controls">
                    <span class="label">Limit</span>
                    <input
                            class="limitInput"
                            type="number"
                            min="1"
                            max="2000"
                            step="50"
                            bind:value={limit}
                            on:change={() => {
              offset = 0;
              loadPage();
            }}
                    />

                    <button class="btn" on:click={prev} disabled={loading || offset === 0}>Prev</button>
                    <button
                            class="btn"
                            on:click={next}
                            disabled={loading || !page || offset + limit >= page.total}
                    >
                        Next
                    </button>

                    {#if page}
                        <span class="pill mono">offset {page.offset}</span>
                        {#if q.trim()}
                            <span class="pill mono">q: {q.trim()}</span>
                        {/if}
                    {/if}
                </div>
            </div>
        </header>

        <div class="tableWrap">
            {#if page && page.items && page.items.length}
                <table class="kittTable">
                    <thead>
                    <tr>
                        {#each cols as c}
                            <th>{c}</th>
                        {/each}
                    </tr>
                    </thead>
                    <tbody>
                    {#each page.items as row}
                        <tr
                                on:dblclick={() =>
                                  goto(`/referential/etfbook/${encodeURIComponent(getValue(row, "fundISIN"))}`)
                                }
                        >
                            {#each cols as c}
                                <td class={c === "Isin" || c === "Symbol" ? "mono" : ""}>
                                    {row?.[c] ?? ""}
                                </td>
                            {/each}
                        </tr>
                    {/each}
                    </tbody>
                </table>
            {:else if page && page.items && !page.items.length}
                <table class="kittTable">
                    <tbody>
                    <tr>
                        <td class="empty">No results.</td>
                    </tr>
                    </tbody>
                </table>
            {:else}
                <table class="kittTable">
                    <tbody>
                    <tr>
                        <td class="empty">No data loaded yet.</td>
                    </tr>
                    </tbody>
                </table>
            {/if}
        </div>
    </section>
</div>
