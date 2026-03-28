<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";
    import { onMount } from "svelte";

    type ArithmeticReturnRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        start_date_used: string;
        end_date_used: string;
        start_price: number;
        end_price: number;
        arithmetic_return: number;
    };

    type ArithmeticReturnResponse = {
        data: ArithmeticReturnRow[];
        errors?: Record<string, string>;
    };

    type HoverState = {
        active: boolean;
        ticker: string;
        returnVal: number;
        startPrice: number;
        endPrice: number;
        startUsed: string;
        endUsed: string;
        x: number;
        y: number;
    };

    let form = {
        tickers: "AAPL,SPY",
        start_date: "",
        end_date: "",
        auto_adjust: true,
        format: "json" as "json" | "csv"
    };

    let isSubmitting = false;
    let errorMessage = "";
    let rows: ArithmeticReturnRow[] = [];
    let errors: Record<string, string> = {};

    let chartWrapEl: HTMLDivElement | null = null;
    let chartRect: DOMRect | null = null;

    const hover: HoverState = {
        active: false,
        ticker: "",
        returnVal: 0,
        startPrice: 0,
        endPrice: 0,
        startUsed: "",
        endUsed: "",
        x: 0,
        y: 0
    };

    const tooltipWidth = 260;
    const tooltipHeight = 130;
    const tooltipPadding = 12;

    function formatPct(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        return `${value.toFixed(2)}%`;
    }

    function formatPrice(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        return value.toFixed(4);
    }

    function formatDate(value: string | null | undefined) {
        if (!value) return "—";
        return value;
    }

    function buildTickers(raw: string) {
        return raw
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);
    }

    function sortRows(list: ArithmeticReturnRow[]) {
        return [...list].sort((a, b) => b.arithmetic_return - a.arithmetic_return);
    }

    function absMax(list: ArithmeticReturnRow[]) {
        const values = list.map((r) => Math.abs(r.arithmetic_return));
        return Math.max(...values, 0.0001);
    }

    function barWidth(value: number, maxValue: number) {
        return `${Math.max((Math.abs(value) / maxValue) * 100, 2)}%`;
    }

    function barColor(value: number, maxValue: number) {
        const ratio = Math.abs(value) / maxValue;
        if (value < 0) return "#ff3355";
        if (ratio >= 0.75) return "#22c55e";
        if (ratio >= 0.5) return "#00d4ff";
        if (ratio >= 0.25) return "#ffcc33";
        return "#00d4ff";
    }

    function updateChartRect() {
        chartRect = chartWrapEl?.getBoundingClientRect() ?? null;
    }

    onMount(() => {
        updateChartRect();
        const onResize = () => updateChartRect();
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    });

    $: tooltipLeft =
        chartRect
            ? Math.min(
                Math.max(hover.x, tooltipPadding),
                chartRect.width - tooltipWidth - tooltipPadding
            )
            : hover.x;

    $: tooltipTop =
        chartRect
            ? Math.min(
                Math.max(hover.y - tooltipHeight / 2, tooltipPadding),
                chartRect.height - tooltipHeight - tooltipPadding
            )
            : hover.y - tooltipHeight / 2;

    function onHoverEnter(e: MouseEvent, row: ArithmeticReturnRow) {
        updateChartRect();

        const target = e.currentTarget as HTMLElement;
        const rect = target.getBoundingClientRect();
        const safeRect = chartRect ?? rect;

        hover.active = true;
        hover.ticker = row.ticker;
        hover.returnVal = row.arithmetic_return;
        hover.startPrice = row.start_price;
        hover.endPrice = row.end_price;
        hover.startUsed = row.start_date_used;
        hover.endUsed = row.end_date_used;

        hover.x = rect.left - safeRect.left + rect.width + 18;
        hover.y = rect.top - safeRect.top + rect.height / 2;
    }

    function onHoverLeave() {
        hover.active = false;
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
        if (!form.start_date) {
            errorMessage = "Start date is required.";
            return;
        }
        if (!form.end_date) {
            errorMessage = "End date is required.";
            return;
        }
        if (form.end_date < form.start_date) {
            errorMessage = "End date must be >= start date.";
            return;
        }

        isSubmitting = true;

        try {
            const payload = {
                tickers,
                start_date: form.start_date,
                end_date: form.end_date,
                auto_adjust: form.auto_adjust
            };

            if (form.format === "csv") {
                const res = await instance.post("/analytics/yahoo/arithmetic-return?format=csv", payload, {
                    responseType: "blob"
                });
                const blob = new Blob([res.data], { type: "text/csv" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "yahoo_arithmetic_return.csv";
                a.click();
                URL.revokeObjectURL(url);
                return;
            }

            const res = await instance.post<ArithmeticReturnResponse>("/analytics/yahoo/arithmetic-return", payload);
            rows = sortRows(res.data?.data ?? []);
            errors = res.data?.errors ?? {};
        } catch (err: any) {
            errorMessage =
                err?.response?.data?.detail ||
                err?.response?.data?.message ||
                err?.message ||
                "Unable to load arithmetic return data.";
        } finally {
            isSubmitting = false;
        }
    }
</script>

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">ARITHMETIC RETURN</h1>
                    <div class="subtitle">
                        Compare returns between two dates with a glowing bar chart sorted by performance.
                    </div>
                </div>

                <div class="statusWrap">
                    <span class="status">YAHOO</span>
                    <span class="status soft">Return analysis</span>
                </div>
            </div>

            <div class="chipRow">
                <span class="chip">Horizontal bar chart</span>
                <span class="chip">Hover tooltip</span>
                <span class="chip">Nearest trading day</span>
                <span class="chip">JSON / CSV</span>
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
                        <span class="label">Format</span>
                        <select class="input" bind:value={form.format}>
                            <option value="json">json</option>
                            <option value="csv">csv</option>
                        </select>
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
                            <div class="summaryK">Start</div>
                            <div class="summaryV mono">{rows[0].start_date_requested}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">End</div>
                            <div class="summaryV mono">{rows[0].end_date_requested}</div>
                        </div>
                    </div>

                    <div class="chartPanel">
                        <div class="chartLegend">
                            <span class="legendPill green">Positive</span>
                            <span class="legendPill red">Negative</span>
                        </div>

                        <div class="barsWrap" bind:this={chartWrapEl}>
                            {#each rows as row}
                                {@const maxV = absMax(rows)}
                                <div
                                        class="barRow"
                                        on:mouseenter={(e) => onHoverEnter(e, row)}
                                        on:mouseleave={onHoverLeave}
                                >
                                    <div class="barHead">
                                        <div class="ticker mono">{row.ticker}</div>
                                        <div class="value mono" class:negative={row.arithmetic_return < 0}>
                                            {formatPct(row.arithmetic_return)}
                                        </div>
                                    </div>

                                    <div class="barTrack">
                                        <div
                                                class="barFill"
                                                style={`width:${barWidth(row.arithmetic_return, maxV)}; background: linear-gradient(90deg, ${barColor(row.arithmetic_return, maxV)}, rgba(255,255,255,0.18));`}
                                        ></div>
                                    </div>

                                    <div class="barMeta">
                                        <span class="mono">{formatPrice(row.start_price)} → {formatPrice(row.end_price)}</span>
                                        <span>{formatDate(row.start_date_used)} → {formatDate(row.end_date_used)}</span>
                                    </div>
                                </div>
                            {/each}

                            {#if hover.active && chartRect}
                                <div
                                        class="tooltip"
                                        style={`left:${tooltipLeft}px; top:${tooltipTop}px;`}
                                >
                                    <div class="tooltipTop">
                                        <span class="tooltipTicker mono">{hover.ticker}</span>
                                        <span class="tooltipDate mono" class:negativeText={hover.returnVal < 0}>
                                            {formatPct(hover.returnVal)}
                                        </span>
                                    </div>

                                    <div class="tooltipValue" class:negativeValue={hover.returnVal < 0}>
                                        {formatPct(hover.returnVal)}
                                    </div>
                                    <div class="tooltipLine">
                                        Start: <span class="mono">{formatPrice(hover.startPrice)}</span>
                                    </div>
                                    <div class="tooltipLine">
                                        End: <span class="mono">{formatPrice(hover.endPrice)}</span>
                                    </div>
                                    <div class="tooltipLine soft">
                                        {hover.startUsed} → {hover.endUsed}
                                    </div>
                                </div>
                            {/if}
                        </div>
                    </div>

<!--                    <div class="tableWrap">-->
<!--                        <table class="kittTable">-->
<!--                            <thead>-->
<!--                            <tr>-->
<!--                                <th>Ticker</th>-->
<!--                                <th>Requested start</th>-->
<!--                                <th>Requested end</th>-->
<!--                                <th>Used start</th>-->
<!--                                <th>Used end</th>-->
<!--                                <th>Start price</th>-->
<!--                                <th>End price</th>-->
<!--                                <th>Arithmetic return</th>-->
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
<!--                                    <td><span class="mono">{formatPrice(row.start_price)}</span></td>-->
<!--                                    <td><span class="mono">{formatPrice(row.end_price)}</span></td>-->
<!--                                    <td>-->
<!--                                        <span class="mono" class:highlight={row.arithmetic_return >= 0} class:negativeHighlight={row.arithmetic_return < 0}>-->
<!--                                            {formatPct(row.arithmetic_return)}-->
<!--                                        </span>-->
<!--                                    </td>-->
<!--                                </tr>-->
<!--                            {/each}-->
<!--                            </tbody>-->
<!--                        </table>-->
<!--                    </div>-->
                {:else}
                    <div class="emptyState">
                        No results yet. Fill the form and run the arithmetic return analysis.
                    </div>
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
        min-height: calc(100vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        background:
                radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
                linear-gradient(180deg, #07080c, #04040a);
    }

    .card {
        width: min(1500px, 100%);
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
        .formGrid {
            grid-template-columns: 1fr;
        }
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .field.full {
        grid-column: 1 / -1;
    }

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
        .summaryRow {
            grid-template-columns: 1fr;
        }
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
        background:
                linear-gradient(180deg, rgba(255, 0, 60, 0.04), rgba(0, 0, 0, 0.16));
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

    .legendPill.green { background: rgba(34, 197, 94, 0.15); }
    .legendPill.red { background: rgba(255, 51, 85, 0.15); }

    .barsWrap {
        display: flex;
        flex-direction: column;
        gap: 12px;
        position: relative;
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
        position: relative;
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
        color: rgba(180, 255, 200, 0.96);
        text-shadow: 0 0 10px rgba(34, 197, 94, 0.20);
    }

    .value.negative {
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
        position: relative;
    }

    .barFill {
        height: 100%;
        border-radius: 999px;
        box-shadow:
                0 0 12px rgba(255, 0, 60, 0.2),
                inset 0 0 16px rgba(255, 255, 255, 0.08);
        transition: width 250ms ease, filter 250ms ease;
    }

    .barRow:hover .barFill {
        filter: brightness(1.1);
    }

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
    }

    .kittTable {
        width: 100%;
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
        color: rgba(180, 255, 200, 0.98);
        text-shadow: 0 0 10px rgba(34, 197, 94, 0.16);
    }

    .negativeHighlight {
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

    .errorRow:first-of-type {
        border-top: 0;
    }

    .tooltip {
        position: absolute;
        z-index: 30;
        width: 260px;
        height: 130px;
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: linear-gradient(180deg, rgba(18, 18, 28, 0.98), rgba(10, 10, 16, 0.98));
        box-shadow:
                0 0 0 1px rgba(255, 0, 60, 0.08),
                0 18px 36px rgba(0, 0, 0, 0.6),
                0 0 24px rgba(255, 0, 60, 0.14);
        backdrop-filter: blur(10px);
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

    .tooltipDate {
        font-size: 11px;
        color: rgba(180, 255, 200, 0.75);
    }

    .tooltipDate.negativeText {
        color: rgba(255, 210, 220, 0.75);
    }

    .tooltipValue {
        font-size: 18px;
        font-weight: 700;
        color: rgba(180, 255, 200, 0.96);
        text-shadow: 0 0 12px rgba(34, 197, 94, 0.24);
        margin-bottom: 6px;
    }

    .tooltipValue.negativeValue {
        color: rgba(255, 210, 220, 0.96);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.24);
    }

    .tooltipLine {
        font-size: 12px;
        color: rgba(235, 235, 245, 0.76);
        margin-top: 4px;
    }

    .tooltipLine.soft {
        color: rgba(235, 235, 245, 0.56);
    }
</style>