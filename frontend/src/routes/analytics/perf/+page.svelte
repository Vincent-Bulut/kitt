<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";

    type PerfRow = {
        ticker: string;
        asof_requested: string | null;
        asof_used: string;
        last: number;
        perf: Record<string, number | null>;
    };

    type PerfResponse = {
        data: PerfRow[];
        errors?: Record<string, string>;
    };

    let form = {
        tickers: "AAPL,SPY",
        asof: "",
        auto_adjust: true
    };

    let isSubmitting = false;
    let errorMessage = "";
    let rows: PerfRow[] = [];
    let errors: Record<string, string> = {};

    const periods = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"];

    function buildTickers(raw: string) {
        return raw.split(",").map((t) => t.trim()).filter(Boolean);
    }

    function formatPct(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${v.toFixed(2)}%`;
    }

    function formatNum(v: number | null | undefined, dec = 2) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return v.toFixed(dec);
    }

    function sortRows(list: PerfRow[]) {
        return [...list].sort((a, b) => {
            const av = a.perf["1Y"] ?? -9999;
            const bv = b.perf["1Y"] ?? -9999;
            return bv - av;
        });
    }

    async function submit() {
        errorMessage = "";
        rows = [];
        errors = {};

        const tickers = buildTickers(form.tickers);
        if (!tickers.length) {
            errorMessage = "Please enter at least one ticker.";
            return;
        }

        isSubmitting = true;
        try {
            const payload = {
                tickers,
                asof: form.asof || null,
                auto_adjust: form.auto_adjust
            };

            const res = await instance.post<PerfResponse>("/analytics/yahoo/perf-table", payload);
            rows = sortRows(res.data?.data ?? []);
            errors = res.data?.errors ?? {};
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.response?.data?.message || err?.message || "Unable to load performance data.";
        } finally {
            isSubmitting = false;
        }
    }
</script>

<div class="page">
    <section class="card">
        <header class="header">
            <h1 class="title">PERFORMANCE</h1>
            <div class="subtitle">Yahoo finance performance table as of a selected date.</div>
        </header>

        <div class="body">
            <div class="formPanel">
                <div class="panelLabel">INPUTS</div>

                <div class="formGrid">
                    <label class="field full">
                        <span class="label">Tickers</span>
                        <input class="input mono" type="text" bind:value={form.tickers} placeholder="AAPL,SPY,AIR.PA" />
                    </label>

                    <label class="field">
                        <span class="label">As of date</span>
                        <input class="input mono" type="date" bind:value={form.asof} />
                    </label>

                    <label class="field toggleField">
                        <input type="checkbox" bind:checked={form.auto_adjust} />
                        <span>Auto adjust prices</span>
                    </label>
                </div>

                {#if errorMessage}
                    <div class="errorBox">{errorMessage}</div>
                {/if}

                <div class="actions">
                    <button class="btn" type="button" on:click={submit} disabled={isSubmitting}>
                        {isSubmitting ? "Running…" : "Run analysis"}
                    </button>
                </div>
            </div>

            <div class="resultsPanel">
                <div class="panelLabel">RESULTS</div>

                {#if rows.length > 0}
                    <div class="summaryRow">
                        <div class="summaryCard">
                            <div class="summaryK">Tickers</div>
                            <div class="summaryV">{rows.length}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">Best 1Y perf</div>
                            <div class="summaryV greenText">{formatPct(rows[0].perf["1Y"])}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">As of</div>
                            <div class="summaryV mono">{rows[0].asof_used}</div>
                        </div>
                    </div>

                    <div class="tableWrap">
                        <table class="kittTable">
                            <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Last</th>
                                {#each periods as p}
                                    <th>{p}</th>
                                {/each}
                                <th>As of used</th>
                            </tr>
                            </thead>
                            <tbody>
                            {#each rows as row (row.ticker)}
                                <tr>
                                    <td><span class="mono">{row.ticker}</span></td>
                                    <td><span class="mono">{formatNum(row.last, 2)}</span></td>
                                    {#each periods as p}
                                        <td>
                                                <span class="mono {((row.perf[p] ?? 0) >= 0) ? 'greenText' : 'redText'}">
                                                    {formatPct(row.perf[p])}
                                                </span>
                                        </td>
                                    {/each}
                                    <td><span class="mono">{row.asof_used}</span></td>
                                </tr>
                            {/each}
                            </tbody>
                        </table>
                    </div>
                {:else}
                    <div class="emptyState">No results yet. Enter tickers and run the analysis.</div>
                {/if}

                {#if Object.keys(errors).length > 0}
                    <div class="errorsPanel">
                        <div class="errorsTitle">ERRORS</div>
                        {#each Object.entries(errors) as [ticker, message]}
                            <div class="errorRow">
                                <span class="mono">{ticker}</span>
                                <span>{message}</span>
                            </div>
                        {/each}
                    </div>
                {/if}
            </div>
        </div>
    </section>
</div>

<style>
    .page {
        min-height: 100vh;
        padding: 5rem 1rem 2rem;
        background: linear-gradient(180deg, #07080c, #04040a);
        color: rgba(255,255,255,0.9);
    }

    .card {
        width: min(1400px, 100%);
        margin: 0 auto;
        border: 1px solid rgba(255, 0, 60, 0.2);
        border-radius: 16px;
        background: rgba(10, 10, 18, 0.95);
        overflow: hidden;
    }

    .header, .body {
        padding: 1rem;
    }

    .header {
        border-bottom: 1px solid rgba(255, 0, 60, 0.12);
    }

    .title {
        margin: 0;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        font-size: 1rem;
    }

    .subtitle {
        margin-top: 0.4rem;
        color: rgba(235, 235, 245, 0.65);
        font-size: 0.9rem;
    }

    .body {
        display: grid;
        gap: 1rem;
    }

    .formPanel, .resultsPanel {
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: rgba(255, 255, 255, 0.02);
        border-radius: 14px;
        padding: 1rem;
    }

    .panelLabel {
        margin-bottom: 0.75rem;
        font-size: 0.78rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.9);
    }

    .formGrid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.75rem;
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }

    .field.full {
        grid-column: 1 / -1;
    }

    .label {
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.6);
    }

    .input {
        width: 100%;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.06);
        color: white;
        padding: 0.75rem 0.85rem;
        outline: none;
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .toggleField {
        flex-direction: row;
        align-items: center;
        gap: 0.65rem;
        color: rgba(235, 235, 245, 0.85);
    }

    .actions {
        margin-top: 1rem;
        display: flex;
        justify-content: flex-end;
    }

    .btn {
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: rgba(255, 0, 60, 0.1);
        color: white;
        border-radius: 12px;
        padding: 0.75rem 1rem;
        cursor: pointer;
    }

    .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .errorBox, .errorsPanel {
        margin-top: 0.85rem;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.25);
        background: rgba(255, 0, 60, 0.08);
        padding: 0.75rem;
    }

    .summaryRow {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin-bottom: 1rem;
    }

    .summaryCard {
        border: 1px solid rgba(255, 0, 60, 0.12);
        background: rgba(255, 255, 255, 0.02);
        border-radius: 12px;
        padding: 0.8rem;
    }

    .summaryK {
        font-size: 0.72rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.55);
        margin-bottom: 0.35rem;
    }

    .summaryV {
        font-size: 1rem;
    }

    .tableWrap {
        overflow: auto;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
    }

    .kittTable {
        width: 100%;
        border-collapse: collapse;
        min-width: 900px;
        background: rgba(0, 0, 0, 0.18);
    }

    .kittTable th, .kittTable td {
        padding: 0.8rem 0.9rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        white-space: nowrap;
        text-align: left;
    }

    .kittTable th {
        position: sticky;
        top: 0;
        background: rgba(20, 20, 30, 0.98);
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }

    .greenText { color: rgba(34, 197, 94, 0.95); }
    .redText { color: rgba(255, 80, 100, 0.96); }

    .emptyState {
        color: rgba(235, 235, 245, 0.62);
        padding: 0.25rem 0;
    }

    .errorsTitle {
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        margin-bottom: 0.5rem;
    }

    .errorRow {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.4rem 0;
    }

    @media (max-width: 900px) {
        .formGrid,
        .summaryRow {
            grid-template-columns: 1fr;
        }
    }
</style>