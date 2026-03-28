<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";

    type CumPoint = {
        date: string;
        cum_return: number;
    };

    type CumSeries = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        start_date_used: string;
        base_price: number;
        points: CumPoint[];
    };

    type CumResponse = {
        data: CumSeries[];
        errors?: Record<string, string>;
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
    let series: CumSeries[] = [];
    let errors: Record<string, string> = {};

    const colors = [
        "#ff3355",
        "#ff6b35",
        "#ffcc33",
        "#00d4ff",
        "#8b5cf6",
        "#22c55e",
        "#f472b6"
    ];

    const chartWidth = 760;
    const chartHeight = 260;
    const chartPad = 26;

    const hoverState = {
        active: false,
        ticker: "",
        date: "",
        value: 0,
        x: 0,
        y: 0
    };

    function buildTickers(raw: string) {
        return raw
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);
    }

    function formatPct(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        return `${(value * 100).toFixed(2)}%`;
    }

    function formatDate(value: string | null | undefined) {
        if (!value) return "—";
        return value;
    }

    function formatPrice(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return "—";
        return value.toFixed(4);
    }

    function latestPoint(points: CumPoint[]) {
        if (!points?.length) return null;
        return points[points.length - 1];
    }

    function buildTickPath(points: CumPoint[]) {
        if (!points?.length) return "";

        const ys = points.map((p) => p.cum_return);
        const minY = Math.min(...ys, 0);
        const maxY = Math.max(...ys, 0);
        const ySpan = Math.max(maxY - minY, 0.0001);
        const xSpan = Math.max(points.length - 1, 1);

        const x = (i: number) => chartPad + (i / xSpan) * (chartWidth - chartPad * 2);
        const y = (v: number) =>
            chartHeight - chartPad - ((v - minY) / ySpan) * (chartHeight - chartPad * 2);

        return points
            .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(p.cum_return).toFixed(2)}`)
            .join(" ");
    }

    function yTicks(points: CumPoint[], count = 5) {
        if (!points?.length) return [];
        const ys = points.map((p) => p.cum_return);
        const minY = Math.min(...ys, 0);
        const maxY = Math.max(...ys, 0);
        const span = Math.max(maxY - minY, 0.0001);

        return Array.from({ length: count }, (_, i) => {
            const ratio = i / (count - 1);
            const value = maxY - ratio * span;
            return {
                value,
                pct: `${(value * 100).toFixed(1)}%`
            };
        });
    }

    function xTicks(points: CumPoint[], count = 5) {
        if (!points?.length) return [];
        const n = points.length;
        const slots = Math.min(count, n);
        const idxs = Array.from({ length: slots }, (_, i) =>
            Math.round((i / Math.max(slots - 1, 1)) * (n - 1))
        );

        return Array.from(new Set(idxs)).map((idx) => ({
            idx,
            label: points[idx]?.date ?? ""
        }));
    }

    function pointStyle(points: CumPoint[], i: number) {
        const ys = points.map((p) => p.cum_return);
        const minY = Math.min(...ys, 0);
        const maxY = Math.max(...ys, 0);
        const ySpan = Math.max(maxY - minY, 0.0001);
        const xSpan = Math.max(points.length - 1, 1);

        const x = chartPad + (i / xSpan) * (chartWidth - chartPad * 2);
        const y =
            chartHeight - chartPad - ((points[i].cum_return - minY) / ySpan) * (chartHeight - chartPad * 2);

        return {
            left: `${(x / chartWidth) * 100}%`,
            top: `${(y / chartHeight) * 100}%`
        };
    }

    function onPointEnter(
        e: MouseEvent,
        ticker: string,
        point: CumPoint
    ) {
        const target = e.currentTarget as HTMLElement;
        const rect = target.getBoundingClientRect();

        hoverState.active = true;
        hoverState.ticker = ticker;
        hoverState.date = point.date;
        hoverState.value = point.cum_return;
        hoverState.x = rect.left + rect.width / 2;
        hoverState.y = rect.top;
    }

    function onPointLeave() {
        hoverState.active = false;
    }

    async function submit() {
        errorMessage = "";
        series = [];
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
                const res = await instance.post("/analytics/yahoo/cumulative-returns?format=csv", payload, {
                    responseType: "blob"
                });

                const blob = new Blob([res.data], { type: "text/csv" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "yahoo_cum_returns.csv";
                a.click();
                URL.revokeObjectURL(url);
                return;
            }

            const res = await instance.post<CumResponse>("/analytics/yahoo/cumulative-returns", payload);
            series = res.data?.data ?? [];
            errors = res.data?.errors ?? {};
        } catch (err: any) {
            errorMessage =
                err?.response?.data?.detail ||
                err?.response?.data?.message ||
                err?.message ||
                "Unable to load cumulative returns.";
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
                    <h1 class="title">CUMULATIVE RETURNS</h1>
                    <div class="subtitle">
                        Product-by-product chart view with date axis and hover tooltips.
                    </div>
                </div>

                <div class="statusWrap">
                    <span class="status">YAHOO</span>
                    <span class="status soft">Chart view</span>
                </div>
            </div>

            <div class="chipRow">
                <span class="chip">Multi-ticker</span>
                <span class="chip">Hover tooltip</span>
                <span class="chip">Date axis</span>
                <span class="chip">JSON / CSV</span>
            </div>
        </header>

        <div class="body">
            <div class="formPanel">
                <div class="panelLabel">INPUTS</div>

                <div class="formGrid">
                    <label class="field full">
                        <span class="label">Tickers</span>
                        <input
                                class="input mono"
                                type="text"
                                bind:value={form.tickers}
                                placeholder="AAPL,SPY,AIR.PA"
                        />
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

                {#if series.length > 0}
                    <div class="summaryRow">
                        <div class="summaryCard">
                            <div class="summaryK">Products</div>
                            <div class="summaryV">{series.length}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">Start</div>
                            <div class="summaryV mono">{series[0].start_date_requested}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">End</div>
                            <div class="summaryV mono">{series[0].end_date_requested}</div>
                        </div>
                    </div>

                    <div class="chartsGrid">
                        {#each series as s, idx (s.ticker)}
                            {@const latest = latestPoint(s.points)}
                            <article class="chartCard">
                                <div class="chartHead">
                                    <div>
                                        <div class="tickerRow">
                                            <span class="ticker mono">{s.ticker}</span>
                                            <span class="legendDot" style={`background:${colors[idx % colors.length]}`}></span>
                                        </div>
                                        <div class="chartMeta">
                                            Base {formatPrice(s.base_price)} · {formatDate(s.start_date_used)} → {formatDate(s.end_date_requested)}
                                        </div>
                                    </div>

                                    <div class="chartBadge">
                                        {formatPct(latest?.cum_return)}
                                    </div>
                                </div>

                                <div class="chartFrame">
                                    <svg viewBox="0 0 760 260" class="chartSvg" preserveAspectRatio="none">
                                        {#each yTicks(s.points) as tick, i}
                                            <line
                                                    x1={chartPad}
                                                    x2={chartWidth - chartPad}
                                                    y1={chartPad + (i * (chartHeight - chartPad * 2)) / 4}
                                                    y2={chartPad + (i * (chartHeight - chartPad * 2)) / 4}
                                                    class="gridLine"
                                            />
                                            <text x="10" y={32 + (i * (chartHeight - chartPad * 2)) / 4} class="axisLabel">
                                                {tick.pct}
                                            </text>
                                        {/each}

                                        {#each xTicks(s.points) as tick}
                                            <line
                                                    x1={chartPad + (tick.idx / Math.max(s.points.length - 1, 1)) * (chartWidth - chartPad * 2)}
                                                    x2={chartPad + (tick.idx / Math.max(s.points.length - 1, 1)) * (chartWidth - chartPad * 2)}
                                                    y1={chartHeight - chartPad}
                                                    y2={chartHeight - chartPad + 7}
                                                    class="xTick"
                                            />
                                            <text
                                                    x={chartPad + (tick.idx / Math.max(s.points.length - 1, 1)) * (chartWidth - chartPad * 2)}
                                                    y={chartHeight - 4}
                                                    class="xAxisLabel"
                                                    text-anchor="middle"
                                            >
                                                {tick.label}
                                            </text>
                                        {/each}

                                        <line x1={chartPad} x2={chartWidth - chartPad} y1={chartHeight - chartPad} y2={chartHeight - chartPad} class="zeroLine" />
                                        <path
                                                d={buildTickPath(s.points)}
                                                fill="none"
                                                stroke={colors[idx % colors.length]}
                                                stroke-width="3.5"
                                                stroke-linecap="round"
                                                stroke-linejoin="round"
                                                class="linePath"
                                        />
                                    </svg>

                                    {#each s.points as pt, i}
                                        <button
                                                class="dot"
                                                type="button"
                                                style={`left:${pointStyle(s.points, i).left}; top:${pointStyle(s.points, i).top}; background:${colors[idx % colors.length]};`}
                                                title={`${pt.date} — ${formatPct(pt.cum_return)}`}
                                                on:mouseenter={(e) => onPointEnter(e, s.ticker, pt)}
                                                on:mouseleave={onPointLeave}
                                        />
                                    {/each}
                                </div>

                                <div class="chartFooter">
                                    <div class="footerStat">
                                        <span class="footerK">Points</span>
                                        <span class="footerV">{s.points.length}</span>
                                    </div>
                                    <div class="footerStat">
                                        <span class="footerK">Last return</span>
                                        <span class="footerV highlight">{formatPct(latest?.cum_return)}</span>
                                    </div>
                                </div>
                            </article>
                        {/each}
                    </div>

                    {#if hoverState.active}
                        <div
                                class="tooltip"
                                style={`left:${Math.min(hoverState.x + 16, window.innerWidth - 260)}px; top:${hoverState.y - 92}px;`}
                        >
                            <div class="tooltipTop">
                                <span class="tooltipTicker mono">{hoverState.ticker}</span>
                                <span class="tooltipDate mono">{hoverState.date}</span>
                            </div>
                            <div class="tooltipValue">{formatPct(hoverState.value)}</div>
                            <div class="tooltipHint">Cumulative return at this date</div>
                        </div>
                    {/if}
                {:else}
                    <div class="emptyState">
                        No results yet. Fill the form and run the cumulative returns analysis.
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

    .chartsGrid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
    }

    @media (max-width: 1100px) {
        .chartsGrid {
            grid-template-columns: 1fr;
        }
    }

    .chartCard {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.16);
        background: rgba(255, 0, 60, 0.05);
        padding: 14px;
    }

    .chartHead {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: flex-start;
        margin-bottom: 12px;
    }

    .tickerRow {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .ticker {
        font-size: 14px;
        letter-spacing: 0.08em;
        color: rgba(255, 255, 255, 0.95);
    }

    .legendDot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        box-shadow: 0 0 12px currentColor;
        flex: none;
    }

    .chartMeta {
        margin-top: 4px;
        font-size: 12px;
        color: rgba(235, 235, 245, 0.6);
    }

    .chartBadge {
        white-space: nowrap;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        padding: 5px 10px;
        border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.08);
    }

    .chartFrame {
        position: relative;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.14);
        background:
                linear-gradient(180deg, rgba(255, 0, 60, 0.05), rgba(0, 0, 0, 0.12)),
                rgba(0, 0, 0, 0.16);
        overflow: hidden;
        min-height: 260px;
    }

    .chartSvg {
        width: 100%;
        height: 260px;
        display: block;
    }

    .gridLine {
        stroke: rgba(255, 255, 255, 0.06);
        stroke-width: 1;
    }

    .xTick {
        stroke: rgba(235, 235, 245, 0.24);
        stroke-width: 1;
    }

    .xAxisLabel {
        fill: rgba(235, 235, 245, 0.5);
        font-size: 10px;
    }

    .zeroLine {
        stroke: rgba(255, 0, 60, 0.28);
        stroke-width: 1.5;
    }

    .axisLabel {
        fill: rgba(235, 235, 245, 0.5);
        font-size: 11px;
    }

    .linePath {
        filter: drop-shadow(0 0 10px rgba(255, 0, 60, 0.18));
    }

    .dot {
        position: absolute;
        width: 9px;
        height: 9px;
        margin-left: -4.5px;
        margin-top: -4.5px;
        border-radius: 999px;
        border: 2px solid rgba(0, 0, 0, 0.7);
        box-shadow: 0 0 12px rgba(255, 255, 255, 0.1);
        opacity: 0.75;
        cursor: pointer;
    }

    .chartFooter {
        margin-top: 12px;
        display: flex;
        justify-content: space-between;
        gap: 10px;
    }

    .footerStat {
        flex: 1;
        border: 1px solid rgba(255, 0, 60, 0.12);
        background: rgba(0, 0, 0, 0.16);
        border-radius: 12px;
        padding: 10px 12px;
    }

    .footerK {
        display: block;
        font-size: 11px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.58);
        margin-bottom: 6px;
    }

    .footerV {
        color: rgba(255, 255, 255, 0.92);
        font-size: 14px;
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

    .errorRow:first-of-type {
        border-top: 0;
    }

    .tooltip {
        position: fixed;
        width: 240px;
        pointer-events: none;
        z-index: 50;
        padding: 10px 12px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.25);
        background:
                linear-gradient(180deg, rgba(20, 20, 30, 0.96), rgba(10, 10, 16, 0.96));
        box-shadow:
                0 0 0 1px rgba(255, 0, 60, 0.08),
                0 16px 30px rgba(0, 0, 0, 0.6),
                0 0 24px rgba(255, 0, 60, 0.18);
        backdrop-filter: blur(10px);
    }

    .tooltipTop {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
        margin-bottom: 8px;
    }

    .tooltipTicker {
        color: rgba(255, 255, 255, 0.95);
        font-size: 12px;
        letter-spacing: 0.08em;
    }

    .tooltipDate {
        color: rgba(255, 210, 220, 0.75);
        font-size: 11px;
    }

    .tooltipValue {
        font-size: 18px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.98);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.28);
    }

    .tooltipHint {
        margin-top: 4px;
        font-size: 11px;
        color: rgba(235, 235, 245, 0.58);
    }
</style>