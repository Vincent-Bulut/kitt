<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";
    import { onMount } from "svelte";

    type VolFrequency = "daily" | "weekly" | "monthly";
    type ReturnMode = "log" | "arith";

    type AnnVolRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        start_date_used: string;
        end_date_used: string;
        observations: number;
        volatility_period: number;
        annualized_volatility: number;
        frequency: VolFrequency;
        price_type: string;
        return_mode: ReturnMode;
    };

    type AnnVolResponse = {
        data: AnnVolRow[];
        errors?: Record<string, string>;
    };

    type HoverState = {
        active: boolean;
        ticker: string;
        annualized: number;
        period: number;
        frequency: VolFrequency | "";
        priceType: string;
        start: string;
        end: string;
        screenX: number;
        screenY: number;
    };

    let form = {
        tickers: "AAPL,SPY",
        start_date: "",
        end_date: "",
        auto_adjust: true,
        frequency: "daily" as VolFrequency,
        return_mode: "log" as ReturnMode
    };

    let isSubmitting = false;
    let errorMessage = "";
    let rows: AnnVolRow[] = [];
    let errors: Record<string, string> = {};

    const hover: HoverState = {
        active: false,
        ticker: "",
        annualized: 0,
        period: 0,
        frequency: "",
        priceType: "",
        start: "",
        end: "",
        screenX: 0,
        screenY: 0
    };

    const tooltipWidth = 264;
    const tooltipHeight = 134;
    const tooltipOffset = 16;

    function formatPct(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        return `${(value * 100).toFixed(2)}%`;
    }

    function formatDate(value: string | null | undefined) {
        if (!value) return "—";
        return value;
    }

    function buildTickers(raw: string) {
        return raw.split(",").map((t) => t.trim()).filter(Boolean);
    }

    function sortRows(list: AnnVolRow[]) {
        return [...list].sort((a, b) => b.annualized_volatility - a.annualized_volatility);
    }

    function maxAnnualized(list: AnnVolRow[]) {
        return Math.max(...list.map((r) => r.annualized_volatility), 0.0001);
    }

    function barWidth(value: number, maxValue: number) {
        return `${Math.max((value / maxValue) * 100, 2)}%`;
    }

    function barColor(value: number, maxValue: number) {
        const ratio = value / maxValue;
        if (ratio >= 0.75) return "#ff3355";
        if (ratio >= 0.5) return "#ff6b35";
        if (ratio >= 0.25) return "#ffcc33";
        return "#00d4ff";
    }

    /* tooltip: use fixed positioning based on window coordinates */
    $: tooltipLeft = (() => {
        const rightEdge = hover.screenX + tooltipOffset + tooltipWidth;
        if (rightEdge > window.innerWidth - 8) {
            return hover.screenX - tooltipOffset - tooltipWidth;
        }
        return hover.screenX + tooltipOffset;
    })();

    $: tooltipTop = Math.min(
        Math.max(hover.screenY - tooltipHeight / 2, 8),
        window.innerHeight - tooltipHeight - 8
    );

    function onHoverEnter(e: MouseEvent, row: AnnVolRow) {
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();

        hover.active = true;
        hover.ticker = row.ticker;
        hover.annualized = row.annualized_volatility;
        hover.period = row.volatility_period;
        hover.frequency = row.frequency;
        hover.priceType = row.price_type;
        hover.start = row.start_date_requested;
        hover.end = row.end_date_requested;
        hover.screenX = rect.right;
        hover.screenY = rect.top + rect.height / 2;
    }

    function onHoverLeave() {
        hover.active = false;
    }

    async function submit() {
        errorMessage = "";
        rows = [];
        errors = {};

        const tickers = buildTickers(form.tickers);
        if (!tickers.length) { errorMessage = "Please enter at least one ticker."; return; }
        if (!form.start_date) { errorMessage = "Start date is required."; return; }
        if (!form.end_date) { errorMessage = "End date is required."; return; }
        if (form.end_date < form.start_date) { errorMessage = "End date must be >= start date."; return; }

        isSubmitting = true;
        try {
            const res = await instance.post<AnnVolResponse>("/analytics/yahoo/annualized-volatility", {
                tickers,
                start_date: form.start_date,
                end_date: form.end_date,
                auto_adjust: form.auto_adjust,
                frequency: form.frequency,
                return_mode: form.return_mode
            });
            rows = sortRows(res.data?.data ?? []);
            errors = res.data?.errors ?? {};
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.response?.data?.message || err?.message || "Unable to load annualized volatility.";
        } finally {
            isSubmitting = false;
        }
    }
</script>

<!-- Fixed tooltip rendered outside the card, no clipping possible -->
{#if hover.active}
    <div
            class="tooltip"
            style={`left:${tooltipLeft}px; top:${tooltipTop}px;`}
    >
        <div class="tooltipTop">
            <span class="tooltipTicker mono">{hover.ticker}</span>
            <span class="tooltipFreq mono">{hover.frequency}</span>
        </div>
        <div class="tooltipValue">{formatPct(hover.annualized)}</div>
        <div class="tooltipLine">Period vol: <span class="mono">{formatPct(hover.period)}</span></div>
        <div class="tooltipLine">Dates: <span class="mono">{hover.start}</span> → <span class="mono">{hover.end}</span></div>
        <div class="tooltipLine soft">{hover.priceType}</div>
    </div>
{/if}

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">ANNUALIZED VOLATILITY</h1>
                    <div class="subtitle">Compare tickers with a glowing bar chart sorted by annualized volatility.</div>
                </div>
                <div class="statusWrap">
                    <span class="status">YAHOO</span>
                    <span class="status soft">Risk / Volatility</span>
                </div>
            </div>
            <div class="chipRow">
                <span class="chip">Horizontal bar chart</span>
                <span class="chip">Hover tooltip</span>
                <span class="chip">Contained inside card</span>
            </div>
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
                        <span class="label">Start date</span>
                        <input class="input mono" type="date" bind:value={form.start_date} />
                    </label>
                    <label class="field">
                        <span class="label">End date</span>
                        <input class="input mono" type="date" bind:value={form.end_date} />
                    </label>
                    <label class="field">
                        <span class="label">Frequency</span>
                        <select class="input" bind:value={form.frequency}>
                            <option value="daily">daily</option>
                            <option value="weekly">weekly</option>
                            <option value="monthly">monthly</option>
                        </select>
                    </label>
                    <label class="field">
                        <span class="label">Return mode</span>
                        <select class="input" bind:value={form.return_mode}>
                            <option value="log">log</option>
                            <option value="arith">arith</option>
                        </select>
                    </label>
                    <label class="field full toggleField">
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
                            <div class="summaryK">Max annualized vol</div>
                            <div class="summaryV highlight">{formatPct(rows[0].annualized_volatility)}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">Frequency</div>
                            <div class="summaryV">{rows[0].frequency}</div>
                        </div>
                    </div>

                    <div class="chartPanel">
                        <div class="chartLegend">
                            <span class="legendPill red">High</span>
                            <span class="legendPill orange">Medium</span>
                            <span class="legendPill cyan">Low</span>
                        </div>

                        <div class="barsWrap">
                            {#each rows as row}
                                {@const maxV = maxAnnualized(rows)}
                                <div
                                        class="barRow"
                                        on:mouseenter={(e) => onHoverEnter(e, row)}
                                        on:mouseleave={onHoverLeave}
                                >
                                    <div class="barHead">
                                        <div class="ticker mono">{row.ticker}</div>
                                        <div class="value mono">{formatPct(row.annualized_volatility)}</div>
                                    </div>
                                    <div class="barTrack">
                                        <div
                                                class="barFill"
                                                style={`width:${barWidth(row.annualized_volatility, maxV)}; background: linear-gradient(90deg, ${barColor(row.annualized_volatility, maxV)}, rgba(255,255,255,0.18));`}
                                        ></div>
                                    </div>
                                    <div class="barMeta">
                                        <span>{row.frequency}</span>
                                        <span>{formatPct(row.volatility_period)} period vol</span>
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>

<!--                    <div class="tableWrap">-->
<!--                        <table class="kittTable">-->
<!--                            <thead>-->
<!--                            <tr>-->
<!--                                <th>Ticker</th>-->
<!--                                <th>Req. start</th>-->
<!--                                <th>Req. end</th>-->
<!--                                <th>Used start</th>-->
<!--                                <th>Used end</th>-->
<!--                                <th>Obs.</th>-->
<!--                                <th>Vol / period</th>-->
<!--                                <th>Annualized vol</th>-->
<!--                                <th>Frequency</th>-->
<!--                                <th>Price type</th>-->
<!--                                <th>Mode</th>-->
<!--                            </tr>-->
<!--                            </thead>-->
<!--                            <tbody>-->
<!--                            {#each rows as row (row.ticker)}-->
<!--                                <tr>-->
<!--                                    <td><span class="mono">{row.ticker}</span></td>-->
<!--                                    <td><span class="mono">{formatDate(row.start_date_requested)}</span></td>-->
<!--                                    <td><span class="mono">{formatDate(row.end_date_requested)}</span></td>-->
<!--                                    <td><span class="mono">{formatDate(row.start_date_used)}</span></td>-->
<!--                                    <td><span class="mono">{formatDate(row.end_date_used)}</span></td>-->
<!--                                    <td><span class="mono">{row.observations}</span></td>-->
<!--                                    <td><span class="mono">{formatPct(row.volatility_period)}</span></td>-->
<!--                                    <td><span class="mono highlight">{formatPct(row.annualized_volatility)}</span></td>-->
<!--                                    <td>{row.frequency}</td>-->
<!--                                    <td>{row.price_type}</td>-->
<!--                                    <td>{row.return_mode}</td>-->
<!--                                </tr>-->
<!--                            {/each}-->
<!--                            </tbody>-->
<!--                        </table>-->
<!--                    </div>-->
                {:else}
                    <div class="emptyState">No results yet. Fill the form and launch the volatility analysis.</div>
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
    /* Fixed tooltip — sits above everything, never clipped */
    .tooltip {
        position: fixed;
        z-index: 9999;
        width: 264px;
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: linear-gradient(180deg, rgba(18, 18, 28, 0.98), rgba(10, 10, 16, 0.98));
        box-shadow:
                0 0 0 1px rgba(255, 0, 60, 0.08),
                0 18px 36px rgba(0, 0, 0, 0.6),
                0 0 24px rgba(255, 0, 60, 0.14);
        backdrop-filter: blur(12px);
        pointer-events: none;
    }

    .tooltipTop {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
    }

    .tooltipTicker {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.95);
        letter-spacing: 0.08em;
    }

    .tooltipFreq {
        font-size: 11px;
        color: rgba(255, 210, 220, 0.75);
    }

    .tooltipValue {
        font-size: 18px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.96);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.24);
        margin-bottom: 6px;
    }

    .tooltipLine {
        font-size: 12px;
        color: rgba(235, 235, 245, 0.76);
        margin-top: 4px;
    }

    .tooltipLine.soft {
        color: rgba(235, 235, 245, 0.56);
    }

    .page {
        min-height: calc(100vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        background:
            radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
            linear-gradient(180deg, #07080c, #04040a);
        overflow-x: hidden;
    }

    .card {
        width: min(1500px, 100%);
        min-width: 0;
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
        flex-wrap: wrap;
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

    .statusWrap {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }

    .status,
    .chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.10);
        box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .status {
        padding: 6px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.88);
    }

    .status.soft {
        background: rgba(255, 0, 60, 0.06);
        color: rgba(255, 255, 255, 0.74);
    }

    .chipRow {
        margin-top: 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }

    .chip {
        padding: 5px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.72);
        background: rgba(255, 0, 60, 0.07);
    }

    .body {
        padding: 16px;
        display: grid;
        gap: 16px;
    }

    .formPanel,
    .resultsPanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 16px;
    }

    .panelLabel {
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
        margin-bottom: 12px;
    }

    .formGrid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
    }

    @media (max-width: 900px) {
        .formGrid { grid-template-columns: 1fr; }
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .field.full { grid-column: 1 / -1; }

    .label {
        font-size: 11px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.58);
    }

    .input {
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.06);
        color: rgba(255, 255, 255, 0.9);
        padding: 10px 12px;
        outline: none;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10);
        transition: border 150ms ease, box-shadow 150ms ease;
    }

    .input:focus {
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 18px rgba(255, 0, 60, 0.18);
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    .toggleField {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 10px;
        color: rgba(235, 235, 245, 0.82);
        margin-top: 2px;
    }

    .errorBox {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.30);
        background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 230, 235, 0.95);
        font-size: 13px;
        line-height: 1.35;
    }

    .actions {
        margin-top: 14px;
        display: flex;
        justify-content: flex-end;
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
        cursor: pointer;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10), 0 0 16px rgba(255, 0, 60, 0.10);
        transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
    }

    .btn:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 20px rgba(255, 0, 60, 0.22);
    }

    .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
    }

    .summaryRow {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 14px;
    }

    @media (max-width: 900px) {
        .summaryRow { grid-template-columns: 1fr; }
    }

    .summaryCard {
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: rgba(255, 0, 60, 0.05);
        border-radius: 12px;
        padding: 10px 12px;
    }

    .summaryK {
        font-size: 11px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.58);
        margin-bottom: 6px;
    }

    .summaryV {
        font-size: 15px;
        color: rgba(255, 255, 255, 0.9);
    }

    .chartPanel {
        margin-bottom: 16px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.04), rgba(0, 0, 0, 0.16));
        padding: 14px;
        position: relative;
        overflow: hidden;
        min-height: 240px;
    }

    .chartLegend {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 12px;
    }

    .legendPill {
        padding: 5px 10px;
        border-radius: 999px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .legendPill.red { background: rgba(255, 51, 85, 0.15); }
    .legendPill.orange { background: rgba(255, 107, 53, 0.15); }
    .legendPill.cyan { background: rgba(0, 212, 255, 0.15); }

    .barsWrap {
        display: flex;
        flex-direction: column;
        gap: 12px;
        overflow: hidden;
        padding-bottom: 4px;
    }

    .barRow {
        display: grid;
        gap: 8px;
        padding: 10px 12px 12px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.12);
        background: rgba(0, 0, 0, 0.18);
        transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
        cursor: pointer;
    }

    .barRow:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.26);
        box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .barHead {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
    }

    .ticker {
        font-size: 13px;
        letter-spacing: 0.08em;
        color: rgba(255, 255, 255, 0.94);
    }

    .value {
        font-size: 13px;
        color: rgba(255, 210, 220, 0.96);
        text-shadow: 0 0 10px rgba(255, 0, 60, 0.16);
    }

    .barTrack {
        height: 16px;
        border-radius: 999px;
        background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(0, 0, 0, 0.18)),
                rgba(255, 255, 255, 0.04);
        overflow: hidden;
        border: 1px solid rgba(255, 0, 60, 0.08);
    }

    .barFill {
        height: 100%;
        border-radius: 999px;
        box-shadow:
                0 0 12px rgba(255, 0, 60, 0.2),
                inset 0 0 16px rgba(255, 255, 255, 0.08);
        transition: width 250ms ease, filter 250ms ease;
    }

    .barRow:hover .barFill { filter: brightness(1.1); }

    .barMeta {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        font-size: 11px;
        color: rgba(235, 235, 245, 0.58);
        letter-spacing: 0.05em;
    }

    .tableWrap {
        max-height: 58vh;
        overflow: auto;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        max-width: 100%;
        width: 100%;
    }

    .kittTable {
        width: max-content;
        min-width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background: rgba(0, 0, 0, 0.25);
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
        white-space: nowrap;
    }

    .kittTable tbody td {
        padding: 12px 14px;
        font-size: 14px;
        color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.10);
        white-space: nowrap;
    }

    .highlight {
        color: rgba(255, 210, 220, 0.98);
        text-shadow: 0 0 10px rgba(255, 0, 60, 0.16);
    }

    .emptyState {
        color: rgba(235, 235, 245, 0.62);
        font-size: 13px;
        line-height: 1.5;
        padding: 4px 2px;
    }

    .errorsPanel {
        margin-top: 14px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(255, 0, 60, 0.05);
        padding: 12px;
    }

    .errorsTitle {
        font-size: 12px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        margin-bottom: 10px;
    }

    .errorRow {
        display: flex;
        gap: 12px;
        justify-content: space-between;
        padding: 8px 0;
        border-top: 1px solid rgba(255, 0, 60, 0.08);
        color: rgba(255, 230, 235, 0.9);
        font-size: 13px;
    }

    .errorRow:first-of-type { border-top: 0; }
</style>