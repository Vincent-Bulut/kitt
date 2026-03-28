<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";

    type DrawdownMetrics = {
        observations: number;
        max_drawdown: number;
        current_drawdown: number;
        num_drawdown_episodes: number;
        avg_drawdown_length_trading_days: number;
        max_drawdown_length_trading_days: number;
        worst_episode_trough: number;
    };

    type DrawdownPath = {
        peak_date: string;
        trough_date: string;
        recovery_date: string | null;
        max_drawdown: number;
    };

    type DrawdownPoint = {
        date: string;
        price: number;
        running_max: number;
        drawdown: number;
    };

    type DrawdownRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        metrics: DrawdownMetrics;
        path: DrawdownPath;
        series?: DrawdownPoint[];
    };

    type DrawdownResponse = {
        data: DrawdownRow[];
        errors?: Record<string, string>;
    };

    type ChartHover = {
        active: boolean;
        date: string;
        drawdown: number;
        price: number;
        screenX: number;
        screenY: number;
    };

    let form = {
        tickers: "AAPL,SPY",
        start_date: "",
        end_date: "",
        auto_adjust: true
    };

    let isSubmitting = false;
    let errorMessage = "";
    let rows: DrawdownRow[] = [];
    let errors: Record<string, string> = {};

    const chartHover: ChartHover = {
        active: false,
        date: "",
        drawdown: 0,
        price: 0,
        screenX: 0,
        screenY: 0
    };

    const tooltipWidth = 240;
    const tooltipHeight = 100;

    const W = 800;
    const H = 200;
    const PAD = { top: 16, right: 16, bottom: 28, left: 52 };

    function formatPct(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${(v * 100).toFixed(2)}%`;
    }

    function formatDate(v: string | null | undefined) {
        if (!v) return "—";
        return v;
    }

    function formatNum(v: number | null | undefined, dec = 1) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return v.toFixed(dec);
    }

    function buildTickers(raw: string) {
        return raw.split(",").map((t) => t.trim()).filter(Boolean);
    }

    function sortRows(list: DrawdownRow[]) {
        return [...list].sort((a, b) => a.metrics.max_drawdown - b.metrics.max_drawdown);
    }

    function maxAbsDD(list: DrawdownRow[]) {
        return Math.max(...list.map((r) => Math.abs(r.metrics.max_drawdown)), 0.0001);
    }

    function barWidth(v: number, maxV: number) {
        return `${Math.max((Math.abs(v) / maxV) * 100, 2)}%`;
    }

    function barColor(v: number, maxV: number) {
        const r = Math.abs(v) / maxV;
        if (r >= 0.75) return "#ff3355";
        if (r >= 0.5) return "#ff6b35";
        if (r >= 0.25) return "#ffcc33";
        return "#00d4ff";
    }

    // ── SVG chart helpers ──────────────────────────────────────

    function buildDDPath(points: DrawdownPoint[]) {
        if (!points?.length) return "";
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const n = points.length;
        const iW = W - PAD.left - PAD.right;
        const iH = H - PAD.top - PAD.bottom;
        const x = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * iW;
        const y = (d: number) => PAD.top + ((maxD - d) / span) * iH;
        return points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.drawdown).toFixed(1)}`).join(" ");
    }

    function buildFillPath(points: DrawdownPoint[]) {
        if (!points?.length) return "";
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const n = points.length;
        const iW = W - PAD.left - PAD.right;
        const iH = H - PAD.top - PAD.bottom;
        const x = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * iW;
        const y = (d: number) => PAD.top + ((maxD - d) / span) * iH;
        const zeroY = y(0);
        const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.drawdown).toFixed(1)}`).join(" ");
        return `${line} L${x(n - 1).toFixed(1)},${zeroY.toFixed(1)} L${x(0).toFixed(1)},${zeroY.toFixed(1)} Z`;
    }

    function yTicks(points: DrawdownPoint[], count = 5) {
        if (!points?.length) return [];
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const iH = H - PAD.top - PAD.bottom;
        return Array.from({ length: count }, (_, i) => {
            const ratio = i / (count - 1);
            const val = maxD - ratio * span;
            const py = PAD.top + ratio * iH;
            return { val, py, label: `${(val * 100).toFixed(0)}%` };
        });
    }

    function xTicks(points: DrawdownPoint[], count = 5) {
        if (!points?.length) return [];
        const n = points.length;
        const iW = W - PAD.left - PAD.right;
        return Array.from({ length: count }, (_, i) => {
            const idx = Math.round((i / (count - 1)) * (n - 1));
            const px = PAD.left + (idx / Math.max(n - 1, 1)) * iW;
            return { label: points[idx]?.date ?? "", px };
        });
    }

    function markerX(points: DrawdownPoint[], date: string) {
        const n = points.length;
        const iW = W - PAD.left - PAD.right;
        const idx = points.findIndex((p) => p.date >= date);
        if (idx < 0) return null;
        return PAD.left + (idx / Math.max(n - 1, 1)) * iW;
    }

    function markerY(points: DrawdownPoint[], date: string) {
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const iH = H - PAD.top - PAD.bottom;
        const idx = points.findIndex((p) => p.date >= date);
        if (idx < 0) return null;
        return PAD.top + ((maxD - points[idx].drawdown) / span) * iH;
    }

    function onChartMouseMove(e: MouseEvent, row: DrawdownRow) {
        if (!row.series?.length) return;
        const svg = e.currentTarget as SVGSVGElement;
        const rect = svg.getBoundingClientRect();
        const relX = (e.clientX - rect.left) * (W / rect.width) - PAD.left;
        const iW = W - PAD.left - PAD.right;
        const n = row.series.length;
        const idx = Math.max(0, Math.min(n - 1, Math.round((relX / iW) * (n - 1))));
        const pt = row.series[idx];
        chartHover.active = true;
        chartHover.date = pt.date;
        chartHover.drawdown = pt.drawdown;
        chartHover.price = pt.price;
        chartHover.screenX = e.clientX;
        chartHover.screenY = e.clientY;
    }

    function onChartMouseLeave() {
        chartHover.active = false;
    }

    $: tooltipLeft = (() => {
        if (typeof window === "undefined") return chartHover.screenX + 16;
        return chartHover.screenX + 16 + tooltipWidth > window.innerWidth - 8
            ? chartHover.screenX - 16 - tooltipWidth
            : chartHover.screenX + 16;
    })();

    $: tooltipTop =
        typeof window !== "undefined"
            ? Math.min(Math.max(chartHover.screenY - tooltipHeight / 2, 8), window.innerHeight - tooltipHeight - 8)
            : chartHover.screenY;

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
            const res = await instance.post<DrawdownResponse>("/analytics/yahoo/drawdowns", {
                tickers,
                start_date: form.start_date,
                end_date: form.end_date,
                auto_adjust: form.auto_adjust,
                include_series: true
            });
            rows = sortRows(res.data?.data ?? []);
            errors = res.data?.errors ?? {};
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.response?.data?.message || err?.message || "Unable to load drawdowns.";
        } finally {
            isSubmitting = false;
        }
    }
</script>

<!-- Chart hover tooltip — fixed, never clipped -->
{#if chartHover.active}
    <div class="tooltip" style={`left:${tooltipLeft}px; top:${tooltipTop}px;`}>
        <div class="ttTop">
            <span class="ttDate mono">{chartHover.date}</span>
        </div>
        <div class="ttDD">{formatPct(chartHover.drawdown)}</div>
        <div class="ttLine">Price: <span class="mono">{chartHover.price.toFixed(2)}</span></div>
    </div>
{/if}

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">DRAWDOWNS</h1>
                    <div class="subtitle">Drawdown series chart with peak, trough and recovery markers per ticker.</div>
                </div>
                <div class="statusWrap">
                    <span class="status">YAHOO</span>
                    <span class="status soft">Risk / Drawdown</span>
                </div>
            </div>
            <div class="chipRow">
                <span class="chip">SVG series chart</span>
                <span class="chip">Peak · Trough · Recovery</span>
                <span class="chip">Hover to inspect</span>
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
                            <div class="summaryK">Worst max drawdown</div>
                            <div class="summaryV redText">{formatPct(rows[0].metrics.max_drawdown)}</div>
                        </div>
                        <div class="summaryCard">
                            <div class="summaryK">Period</div>
                            <div class="summaryV mono">{rows[0].start_date_requested} → {rows[0].end_date_requested}</div>
                        </div>
                    </div>

                    <!-- Per-ticker drawdown series charts -->
                    <div class="chartsSection">
                        {#each rows as row}
                            <div class="tickerChartBlock">
                                <div class="tcHeader">
                                    <div class="tcTicker mono">{row.ticker}</div>
                                    <div class="tcMeta">
                                        <span class="redText">{formatPct(row.metrics.max_drawdown)}</span>
                                        <span class="muted">·</span>
                                        <span>{row.metrics.num_drawdown_episodes} episodes</span>
                                        <span class="muted">·</span>
                                        <span>Avg {formatNum(row.metrics.avg_drawdown_length_trading_days)} days</span>
                                    </div>
                                </div>

                                {#if row.series?.length}
                                    <div class="chartFrame">
                                        <svg
                                                viewBox={`0 0 ${W} ${H}`}
                                                preserveAspectRatio="none"
                                                class="ddSvg"
                                                on:mousemove={(e) => onChartMouseMove(e, row)}
                                                on:mouseleave={onChartMouseLeave}
                                                role="img"
                                        >
                                            <!-- Grid lines -->
                                            {#each yTicks(row.series) as tick}
                                                <line x1={PAD.left} x2={W - PAD.right} y1={tick.py} y2={tick.py} class="gridLine" />
                                                <text x={PAD.left - 4} y={tick.py + 4} class="axisLabel" text-anchor="end">{tick.label}</text>
                                            {/each}

                                            <!-- Zero line -->
                                            {#if true}
                                                {@const dds = row.series.map((p) => p.drawdown)}
                                                {@const minD = Math.min(...dds, 0)}
                                                {@const maxD = Math.max(...dds, 0)}
                                                {@const span = Math.max(maxD - minD, 0.0001)}
                                                {@const iH = H - PAD.top - PAD.bottom}
                                                {@const zeroY = PAD.top + ((maxD - 0) / span) * iH}
                                                <line x1={PAD.left} x2={W - PAD.right} y1={zeroY} y2={zeroY} class="zeroLine" />
                                            {/if}

                                            <!-- X ticks -->
                                            {#each xTicks(row.series) as tick}
                                                <text x={tick.px} y={H - PAD.bottom + 14} class="xLabel" text-anchor="middle">{tick.label}</text>
                                            {/each}

                                            <!-- Fill area -->
                                            <path d={buildFillPath(row.series)} class="ddFill" />

                                            <!-- Line -->
                                            <path d={buildDDPath(row.series)} class="ddLine" />

                                            <!-- Peak marker -->
                                            {#if markerX(row.series, row.path.peak_date) !== null && markerY(row.series, row.path.peak_date) !== null}
                                                {@const px = markerX(row.series, row.path.peak_date)!}
                                                {@const py = markerY(row.series, row.path.peak_date)!}
                                                <line x1={px} x2={px} y1={PAD.top} y2={H - PAD.bottom} class="markerLine peakLine" />
                                                <circle cx={px} cy={py} r={5} class="markerDot peakDot" />
                                                <text x={px + 6} y={PAD.top + 14} class="markerLabel peakLabel">Peak</text>
                                            {/if}

                                            <!-- Trough marker -->
                                            {#if markerX(row.series, row.path.trough_date) !== null && markerY(row.series, row.path.trough_date) !== null}
                                                {@const tx = markerX(row.series, row.path.trough_date)!}
                                                {@const ty = markerY(row.series, row.path.trough_date)!}
                                                <line x1={tx} x2={tx} y1={PAD.top} y2={H - PAD.bottom} class="markerLine troughLine" />
                                                <circle cx={tx} cy={ty} r={5} class="markerDot troughDot" />
                                                <text x={tx + 6} y={H - PAD.bottom - 6} class="markerLabel troughLabel">{formatPct(row.path.max_drawdown)}</text>
                                            {/if}

                                            <!-- Recovery marker -->
                                            {#if row.path.recovery_date && markerX(row.series, row.path.recovery_date) !== null}
                                                {@const rx = markerX(row.series, row.path.recovery_date)!}
                                                <line x1={rx} x2={rx} y1={PAD.top} y2={H - PAD.bottom} class="markerLine recoveryLine" />
                                                <circle cx={rx} cy={markerY(row.series, row.path.recovery_date) ?? PAD.top} r={5} class="markerDot recoveryDot" />
                                                <text x={rx + 6} y={PAD.top + 14} class="markerLabel recoveryLabel">Recovery</text>
                                            {/if}
                                        </svg>

                                        <!-- Legend -->
                                        <div class="chartLegend">
                                            <span class="lDot peakColor"></span><span class="lLabel">Peak</span>
                                            <span class="lDot troughColor"></span><span class="lLabel">Trough</span>
                                            {#if row.path.recovery_date}
                                                <span class="lDot recoveryColor"></span><span class="lLabel">Recovery</span>
                                            {:else}
                                                <span class="lLabel muted">Not recovered</span>
                                            {/if}
                                        </div>
                                    </div>
                                {:else}
                                    <div class="noSeries">No series data available.</div>
                                {/if}

                                <!-- Metrics strip below chart -->
                                <div class="metricsStrip">
                                    <div class="metricBit">
                                        <div class="mK">Current DD</div>
                                        <div class="mV mono">{formatPct(row.metrics.current_drawdown)}</div>
                                    </div>
                                    <div class="metricBit">
                                        <div class="mK">Worst trough</div>
                                        <div class="mV mono redText">{formatPct(row.metrics.worst_episode_trough)}</div>
                                    </div>
                                    <div class="metricBit">
                                        <div class="mK">Max episode</div>
                                        <div class="mV mono">{row.metrics.max_drawdown_length_trading_days}d</div>
                                    </div>
                                    <div class="metricBit">
                                        <div class="mK">Avg episode</div>
                                        <div class="mV mono">{formatNum(row.metrics.avg_drawdown_length_trading_days)}d</div>
                                    </div>
                                    <div class="metricBit">
                                        <div class="mK">Peak date</div>
                                        <div class="mV mono">{formatDate(row.path.peak_date)}</div>
                                    </div>
                                    <div class="metricBit">
                                        <div class="mK">Trough date</div>
                                        <div class="mV mono">{formatDate(row.path.trough_date)}</div>
                                    </div>
                                </div>
                            </div>
                        {/each}
                    </div>

                    <!-- Summary table -->
                    <div class="tableWrap">
                        <table class="kittTable">
                            <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Max DD</th>
                                <th>Current DD</th>
                                <th>Episodes</th>
                                <th>Avg days</th>
                                <th>Max days</th>
                                <th>Worst trough</th>
                                <th>Observations</th>
                            </tr>
                            </thead>
                            <tbody>
                            {#each rows as row (row.ticker)}
                                <tr>
                                    <td><span class="mono">{row.ticker}</span></td>
                                    <td><span class="mono redText">{formatPct(row.metrics.max_drawdown)}</span></td>
                                    <td><span class="mono">{formatPct(row.metrics.current_drawdown)}</span></td>
                                    <td><span class="mono">{row.metrics.num_drawdown_episodes}</span></td>
                                    <td><span class="mono">{formatNum(row.metrics.avg_drawdown_length_trading_days)}</span></td>
                                    <td><span class="mono">{row.metrics.max_drawdown_length_trading_days}</span></td>
                                    <td><span class="mono redText">{formatPct(row.metrics.worst_episode_trough)}</span></td>
                                    <td><span class="mono">{row.metrics.observations}</span></td>
                                </tr>
                            {/each}
                            </tbody>
                        </table>
                    </div>
                {:else}
                    <div class="emptyState">No results yet. Fill the form and run the drawdown analysis.</div>
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
    .tooltip {
        position: fixed;
        z-index: 9999;
        width: 240px;
        padding: 10px 12px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: linear-gradient(180deg, rgba(18, 18, 28, 0.98), rgba(10, 10, 16, 0.98));
        box-shadow: 0 0 0 1px rgba(255, 0, 60, 0.08), 0 18px 36px rgba(0, 0, 0, 0.6), 0 0 24px rgba(255, 0, 60, 0.14);
        backdrop-filter: blur(12px);
        pointer-events: none;
    }

    .ttTop { display: flex; justify-content: space-between; margin-bottom: 6px; }
    .ttDate { font-size: 11px; color: rgba(235, 235, 245, 0.68); letter-spacing: 0.06em; }
    .ttDD { font-size: 18px; font-weight: 700; color: rgba(255, 80, 100, 0.96); text-shadow: 0 0 12px rgba(255, 0, 60, 0.28); margin-bottom: 4px; }
    .ttLine { font-size: 12px; color: rgba(235, 235, 245, 0.76); }

    .page {
        min-height: calc(100vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        overflow-x: hidden;
        background:
                radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
                linear-gradient(180deg, #07080c, #04040a);
    }

    .card {
        width: min(1500px, 100%);
        min-width: 0;
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow: 0 0 0 1px rgba(255, 0, 60, 0.08), 0 20px 60px rgba(0, 0, 0, 0.65), 0 0 30px rgba(255, 0, 60, 0.08);
        overflow: hidden;
        position: relative;
    }

    .scanline {
        position: absolute; inset: 0; pointer-events: none;
        background: linear-gradient(180deg, transparent, rgba(255, 0, 60, 0.08), transparent);
        height: 120px; transform: translateY(-120px);
        animation: scan 4.5s linear infinite; opacity: 0.75;
    }

    @keyframes scan {
        0% { transform: translateY(-120px); }
        100% { transform: translateY(320px); }
    }

    .header {
        position: relative; padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background:
                linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
                linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }

    .headerTop { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; flex-wrap: wrap; }

    .title { margin: 0; font-size: 14px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(255, 0, 60, 0.95); text-shadow: 0 0 12px rgba(255, 0, 60, 0.35); }
    .subtitle { margin-top: 6px; font-size: 12px; color: rgba(235, 235, 245, 0.65); }
    .statusWrap { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }

    .status, .chip {
        display: inline-flex; align-items: center;
        border-radius: 999px; border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.10); box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .status { padding: 6px 10px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(255, 255, 255, 0.88); }
    .status.soft { background: rgba(255, 0, 60, 0.06); color: rgba(255, 255, 255, 0.74); }
    .chipRow { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
    .chip { padding: 5px 10px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(235, 235, 245, 0.72); background: rgba(255, 0, 60, 0.07); }

    .body { padding: 16px; display: grid; gap: 16px; min-width: 0; }

    .formPanel, .resultsPanel {
        border-radius: 14px; border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22); padding: 16px; min-width: 0;
    }

    .panelLabel { font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase; color: rgba(255, 0, 60, 0.95); text-shadow: 0 0 12px rgba(255, 0, 60, 0.25); margin-bottom: 12px; }

    .formGrid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

    @media (max-width: 900px) { .formGrid { grid-template-columns: 1fr; } }

    .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .field.full { grid-column: 1 / -1; }

    .label { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(235, 235, 245, 0.58); }

    .input {
        border-radius: 12px; border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.06); color: rgba(255, 255, 255, 0.9);
        padding: 10px 12px; outline: none; width: 100%;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10);
        transition: border 150ms ease, box-shadow 150ms ease;
    }

    .input:focus { border-color: rgba(255, 0, 60, 0.55); box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 18px rgba(255, 0, 60, 0.18); }

    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }

    .toggleField { display: flex; flex-direction: row; align-items: center; gap: 10px; color: rgba(235, 235, 245, 0.82); }

    .errorBox { margin-top: 12px; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255, 0, 60, 0.30); background: rgba(255, 0, 60, 0.10); color: rgba(255, 230, 235, 0.95); font-size: 13px; line-height: 1.35; }

    .actions { margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px; }

    .btn {
        display: inline-flex; align-items: center; justify-content: center;
        padding: 10px 12px; border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.28); background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 255, 255, 0.9); font-size: 13px; letter-spacing: 0.04em;
        cursor: pointer; flex-shrink: 0;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10), 0 0 16px rgba(255, 0, 60, 0.10);
        transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
    }

    .btn:hover { transform: translateY(-1px); border-color: rgba(255, 0, 60, 0.55); box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 20px rgba(255, 0, 60, 0.22); }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; }

    .summaryRow { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }

    @media (max-width: 900px) { .summaryRow { grid-template-columns: 1fr; } }

    .summaryCard { border: 1px solid rgba(255, 0, 60, 0.14); background: rgba(255, 0, 60, 0.05); border-radius: 12px; padding: 10px 12px; min-width: 0; }
    .summaryK { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(235, 235, 245, 0.58); margin-bottom: 6px; }
    .summaryV { font-size: 15px; color: rgba(255, 255, 255, 0.9); }

    /* Charts section */
    .chartsSection { display: grid; gap: 14px; margin-bottom: 16px; }

    .tickerChartBlock {
        border-radius: 14px; border: 1px solid rgba(255, 0, 60, 0.16);
        background: rgba(255, 0, 60, 0.04); padding: 14px; min-width: 0;
    }

    .tcHeader { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
    .tcTicker { font-size: 14px; letter-spacing: 0.08em; color: rgba(255, 255, 255, 0.96); }
    .tcMeta { display: flex; gap: 8px; align-items: center; font-size: 12px; color: rgba(235, 235, 245, 0.65); flex-wrap: wrap; }
    .muted { opacity: 0.5; }

    .chartFrame {
        border-radius: 12px; border: 1px solid rgba(255, 0, 60, 0.12);
        background: rgba(0, 0, 0, 0.20); overflow: hidden;
    }

    .ddSvg { width: 100%; height: 200px; display: block; cursor: crosshair; }

    .gridLine { stroke: rgba(255, 255, 255, 0.06); stroke-width: 1; }
    .zeroLine { stroke: rgba(255, 255, 255, 0.22); stroke-width: 1; stroke-dasharray: 4 4; }
    .axisLabel { fill: rgba(235, 235, 245, 0.50); font-size: 11px; }
    .xLabel { fill: rgba(235, 235, 245, 0.45); font-size: 10px; }

    .ddFill { fill: rgba(255, 0, 60, 0.18); }
    .ddLine { fill: none; stroke: rgba(255, 51, 85, 0.85); stroke-width: 2; stroke-linejoin: round; filter: drop-shadow(0 0 6px rgba(255, 0, 60, 0.35)); }

    /* Markers */
    .markerLine { stroke-width: 1.5; stroke-dasharray: 4 3; opacity: 0.75; }
    .peakLine { stroke: rgba(255, 204, 0, 0.8); }
    .troughLine { stroke: rgba(255, 51, 85, 0.9); }
    .recoveryLine { stroke: rgba(34, 197, 94, 0.8); }

    .markerDot { stroke-width: 2; }
    .peakDot { fill: rgba(255, 204, 0, 0.9); stroke: rgba(0, 0, 0, 0.5); }
    .troughDot { fill: rgba(255, 51, 85, 0.95); stroke: rgba(0, 0, 0, 0.5); }
    .recoveryDot { fill: rgba(34, 197, 94, 0.9); stroke: rgba(0, 0, 0, 0.5); }

    .markerLabel { font-size: 11px; }
    .peakLabel { fill: rgba(255, 204, 0, 0.9); }
    .troughLabel { fill: rgba(255, 100, 120, 0.95); }
    .recoveryLabel { fill: rgba(34, 197, 94, 0.9); }

    .chartLegend { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-top: 1px solid rgba(255, 0, 60, 0.08); }
    .lDot { width: 10px; height: 10px; border-radius: 999px; flex-shrink: 0; }
    .peakColor { background: rgba(255, 204, 0, 0.9); }
    .troughColor { background: rgba(255, 51, 85, 0.95); }
    .recoveryColor { background: rgba(34, 197, 94, 0.9); }
    .lLabel { font-size: 11px; color: rgba(235, 235, 245, 0.70); letter-spacing: 0.06em; text-transform: uppercase; }

    .noSeries { padding: 16px; color: rgba(235, 235, 245, 0.55); font-size: 13px; }

    .metricsStrip {
        display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 8px; margin-top: 10px;
    }

    @media (max-width: 900px) { .metricsStrip { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    @media (max-width: 600px) { .metricsStrip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

    .metricBit { border: 1px solid rgba(255, 0, 60, 0.10); background: rgba(0, 0, 0, 0.14); border-radius: 10px; padding: 8px 10px; min-width: 0; }
    .mK { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(235, 235, 245, 0.52); margin-bottom: 4px; }
    .mV { font-size: 13px; color: rgba(255, 255, 255, 0.88); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    /* Table */
    .tableWrap { overflow: auto; max-height: 55vh; max-width: 100%; border-radius: 14px; border: 1px solid rgba(255, 0, 60, 0.18); }

    .kittTable { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; background: rgba(0, 0, 0, 0.25); }

    .kittTable thead th {
        text-align: left; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
        padding: 14px 14px; border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky; top: 0; z-index: 1; white-space: nowrap;
    }

    .kittTable tbody td { padding: 12px 14px; font-size: 14px; color: rgba(235, 235, 245, 0.85); border-bottom: 1px solid rgba(255, 0, 60, 0.10); white-space: nowrap; }

    .redText { color: rgba(255, 80, 100, 0.96); text-shadow: 0 0 10px rgba(255, 0, 60, 0.18); }
    .emptyState { color: rgba(235, 235, 245, 0.62); font-size: 13px; line-height: 1.5; padding: 4px 2px; }

    .errorsPanel { margin-top: 14px; border-radius: 12px; border: 1px solid rgba(255, 0, 60, 0.18); background: rgba(255, 0, 60, 0.05); padding: 12px; }
    .errorsTitle { font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255, 0, 60, 0.95); margin-bottom: 10px; }
    .errorRow { display: flex; gap: 12px; justify-content: space-between; padding: 8px 0; border-top: 1px solid rgba(255, 0, 60, 0.08); color: rgba(255, 230, 235, 0.9); font-size: 13px; }
    .errorRow:first-of-type { border-top: 0; }
</style>