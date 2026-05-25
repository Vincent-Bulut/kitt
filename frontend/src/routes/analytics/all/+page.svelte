<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";

    type PerfRow = {
        ticker: string;
        asof_used: string;
        last: number;
        perf: Record<string, number | null>;
    };

    type ArithRow = {
        ticker: string;
        start_date_used: string;
        end_date_used: string;
        start_price: number;
        end_price: number;
        arithmetic_return: number;
    };

    type CumPoint = { date: string; cum_return: number };
    type CumSeries = {
        ticker: string;
        start_date_used: string;
        base_price: number;
        points: CumPoint[];
    };

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
    type DrawdownPoint = { date: string; price: number; running_max: number; drawdown: number };
    type DrawdownRow = {
        ticker: string;
        metrics: DrawdownMetrics;
        path: DrawdownPath;
        series?: DrawdownPoint[];
    };

    type AnnVolRow = {
        ticker: string;
        observations: number;
        volatility_period: number;
        annualized_volatility: number;
        frequency: string;
        price_type: string;
        return_mode: string;
    };

    type VaREsPoint = {
        confidence_level: number;
        var_historical: number;
        es_historical: number;
        var_gaussian: number;
        es_gaussian: number;
        var_cornish_fisher: number;
        es_cf_empirical_tail: number;
    };
    type VaREsFlat = VaREsPoint & {
        ticker: string;
        observations: number;
        start_date_used: string;
        end_date_used: string;
    };

    let form = {
        tickers: "AAPL,SPY",
        asof: "",
        start_date: "",
        end_date: "",
        auto_adjust: true,
        frequency: "daily",
        return_mode: "arith",
        confidence_levels: "0.95,0.99"
    };

    let isSubmitting = false;
    let errorMessage = "";

    let perfRows: PerfRow[] = [];
    let arithRows: ArithRow[] = [];
    let cumSeries: CumSeries[] = [];
    let ddRows: DrawdownRow[] = [];
    let volRows: AnnVolRow[] = [];
    let varEsRows: VaREsFlat[] = [];

    let perfErrors: Record<string, string> = {};
    let arithErrors: Record<string, string> = {};
    let cumErrors: Record<string, string> = {};
    let ddErrors: Record<string, string> = {};
    let volErrors: Record<string, string> = {};
    let riskErrors: Record<string, string> = {};

    let moduleStatus: Record<string, "idle" | "loading" | "ok" | "error"> = {
        perf: "idle",
        arith: "idle",
        cum: "idle",
        dd: "idle",
        vol: "idle",
        var: "idle"
    };

    const periods = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"];
    const lineColors = ["#ff3355", "#ff6b35", "#ffcc33", "#00d4ff", "#8b5cf6", "#22c55e", "#f472b6"];

    const CW = 760;
    const CH = 220;
    const CP = 28;
    const DW = 760;
    const DH = 180;
    const DPAD = { top: 14, right: 14, bottom: 24, left: 48 };

    function buildTickers(raw: string) {
        return raw.split(",").map((t) => t.trim()).filter(Boolean);
    }

    function formatPct(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${v.toFixed(2)}%`;
    }

    function formatPctFrac(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${(v * 100).toFixed(2)}%`;
    }

    function formatNum(v: number | null | undefined, dec = 2) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return v.toFixed(dec);
    }

    function arithBarWidth(value: number, maxAbs: number) {
        return `${Math.max((Math.abs(value) / Math.max(maxAbs, 0.0001)) * 100, 2)}%`;
    }

    function volBarWidth(value: number, max: number) {
        return `${Math.max((value / Math.max(max, 0.0001)) * 100, 2)}%`;
    }

    function buildCumPath(points: CumPoint[]) {
        if (!points?.length) return "";
        const ys = points.map((p) => p.cum_return);
        const minY = Math.min(...ys, 0);
        const maxY = Math.max(...ys, 0);
        const span = Math.max(maxY - minY, 0.0001);
        const xSpan = Math.max(points.length - 1, 1);
        const x = (i: number) => CP + (i / xSpan) * (CW - CP * 2);
        const y = (v: number) => CH - CP - ((v - minY) / span) * (CH - CP * 2);
        return points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(p.cum_return).toFixed(2)}`).join(" ");
    }

    function buildDDLine(points: DrawdownPoint[]) {
        if (!points?.length) return "";
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const iW = DW - DPAD.left - DPAD.right;
        const iH = DH - DPAD.top - DPAD.bottom;
        const n = points.length;
        const x = (i: number) => DPAD.left + (i / Math.max(n - 1, 1)) * iW;
        const y = (d: number) => DPAD.top + ((maxD - d) / span) * iH;
        return points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.drawdown).toFixed(1)}`).join(" ");
    }

    function buildDDFill(points: DrawdownPoint[]) {
        if (!points?.length) return "";
        const dds = points.map((p) => p.drawdown);
        const minD = Math.min(...dds, 0);
        const maxD = Math.max(...dds, 0);
        const span = Math.max(maxD - minD, 0.0001);
        const iW = DW - DPAD.left - DPAD.right;
        const iH = DH - DPAD.top - DPAD.bottom;
        const n = points.length;
        const x = (i: number) => DPAD.left + (i / Math.max(n - 1, 1)) * iW;
        const y = (d: number) => DPAD.top + ((maxD - d) / span) * iH;
        const zeroY = y(0);
        const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.drawdown).toFixed(1)}`).join(" ");
        return `${line} L${x(n - 1).toFixed(1)},${zeroY.toFixed(1)} L${x(0).toFixed(1)},${zeroY.toFixed(1)} Z`;
    }

    async function submit() {
        errorMessage = "";
        perfRows = []; arithRows = []; cumSeries = []; ddRows = []; volRows = []; varEsRows = [];
        perfErrors = {}; arithErrors = {}; cumErrors = {}; ddErrors = {}; volErrors = {}; riskErrors = {};
        moduleStatus = { perf: "idle", arith: "idle", cum: "idle", dd: "idle", vol: "idle", var: "idle" };

        const tickers = buildTickers(form.tickers);
        if (!tickers.length) { errorMessage = "Please enter at least one ticker."; return; }
        if (!form.start_date) { errorMessage = "Start date is required."; return; }
        if (!form.end_date) { errorMessage = "End date is required."; return; }
        if (form.end_date < form.start_date) { errorMessage = "End date must be >= start date."; return; }

        const confidence_levels = form.confidence_levels
            .split(",")
            .map((x) => Number(x.trim()))
            .filter((x) => !Number.isNaN(x) && x > 0 && x < 1);
        if (!confidence_levels.length) {
            errorMessage = "Enter at least one valid confidence level, e.g. 0.95,0.99.";
            return;
        }

        const base = { tickers, start_date: form.start_date, end_date: form.end_date, auto_adjust: form.auto_adjust };
        moduleStatus = { perf: "loading", arith: "loading", cum: "loading", dd: "loading", vol: "loading", var: "loading" };
        isSubmitting = true;

        const perfPromise = instance.post("/analytics/yahoo/perf-table", {
            tickers,
            asof: form.asof || null,
            auto_adjust: form.auto_adjust
        });
        const arithPromise = instance.post("/analytics/yahoo/arithmetic-return", base);
        const cumPromise = instance.post("/analytics/yahoo/cumulative-returns", base);
        const ddPromise = instance.post("/analytics/yahoo/drawdowns", { ...base, include_series: true });
        const volPromise = instance.post("/analytics/yahoo/annualized-volatility", {
            ...base,
            frequency: form.frequency,
            return_mode: form.return_mode
        });
        const varPromise = instance.post("/analytics/yahoo/var-es", {
            ...base,
            return_mode: form.return_mode,
            confidence_levels
        });

        const results = await Promise.allSettled([
            perfPromise, arithPromise, cumPromise, ddPromise, volPromise, varPromise
        ]);

        if (results[0].status === "fulfilled") {
            perfRows = [...(results[0].value.data?.data ?? [])].sort((a: PerfRow, b: PerfRow) => (b.perf["1Y"] ?? -9999) - (a.perf["1Y"] ?? -9999));
            perfErrors = results[0].value.data?.errors ?? {};
            moduleStatus.perf = "ok";
        } else { moduleStatus.perf = "error"; }

        if (results[1].status === "fulfilled") {
            arithRows = [...(results[1].value.data?.data ?? [])].sort((a: ArithRow, b: ArithRow) => b.arithmetic_return - a.arithmetic_return);
            arithErrors = results[1].value.data?.errors ?? {};
            moduleStatus.arith = "ok";
        } else { moduleStatus.arith = "error"; }

        if (results[2].status === "fulfilled") {
            cumSeries = results[2].value.data?.data ?? [];
            cumErrors = results[2].value.data?.errors ?? {};
            moduleStatus.cum = "ok";
        } else { moduleStatus.cum = "error"; }

        if (results[3].status === "fulfilled") {
            ddRows = [...(results[3].value.data?.data ?? [])].sort((a: DrawdownRow, b: DrawdownRow) => a.metrics.max_drawdown - b.metrics.max_drawdown);
            ddErrors = results[3].value.data?.errors ?? {};
            moduleStatus.dd = "ok";
        } else { moduleStatus.dd = "error"; }

        if (results[4].status === "fulfilled") {
            volRows = [...(results[4].value.data?.data ?? [])].sort((a: AnnVolRow, b: AnnVolRow) => b.annualized_volatility - a.annualized_volatility);
            volErrors = results[4].value.data?.errors ?? {};
            moduleStatus.vol = "ok";
        } else { moduleStatus.vol = "error"; }

        if (results[5].status === "fulfilled") {
            const flat: VaREsFlat[] = [];
            for (const row of results[5].value.data?.data ?? []) {
                for (const pt of row.points ?? []) {
                    flat.push({
                        ticker: row.ticker,
                        observations: row.observations,
                        start_date_used: row.start_date_used,
                        end_date_used: row.end_date_used,
                        ...pt
                    });
                }
            }
            varEsRows = flat;
            riskErrors = results[5].value.data?.errors ?? {};
            moduleStatus.var = "ok";
        } else { moduleStatus.var = "error"; }

        isSubmitting = false;

        const allFailed = Object.values(moduleStatus).every((s) => s === "error");
        if (allFailed) errorMessage = "All modules failed. Check API connectivity.";
    }

    $: arithMaxAbs = arithRows.length ? Math.max(...arithRows.map((r) => Math.abs(r.arithmetic_return))) : 0.0001;
    $: volMax = volRows.length ? Math.max(...volRows.map((r) => r.annualized_volatility)) : 0.0001;
</script>

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">ALL ANALYTICS — ONE COCKPIT</h1>
                    <div class="subtitle">
                        Single form, parallel fetch across all 6 analytics modules.
                    </div>
                </div>
                <div class="statusWrap">
                    <span class="status">LIVE</span>
                    <span class="status soft">Yahoo</span>
                </div>
            </div>
            <div class="chipRow">
                <span class="chip">Perf</span>
                <span class="chip">Arithmetic</span>
                <span class="chip">Cumulative</span>
                <span class="chip">Drawdowns</span>
                <span class="chip">Volatility</span>
                <span class="chip">VaR / ES</span>
            </div>
        </header>

        <div class="body">
            <div class="formPanel">
                <div class="panelLabel">SHARED INPUTS</div>

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
                        <span class="label">As of (perf table)</span>
                        <input class="input mono" type="date" bind:value={form.asof} />
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
                            <option value="arith">arith</option>
                            <option value="log">log</option>
                        </select>
                    </label>
                    <label class="field">
                        <span class="label">Confidence levels</span>
                        <input class="input mono" type="text" bind:value={form.confidence_levels} placeholder="0.95,0.99" />
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
                        {isSubmitting ? "Running 6 modules…" : "Run all analytics"}
                    </button>
                </div>

                <div class="moduleStatusRow">
                    {#each Object.entries(moduleStatus) as [key, status]}
                        <span class="statusPill" data-status={status}>{key.toUpperCase()}: {status}</span>
                    {/each}
                </div>
            </div>

            <!-- PERFORMANCE -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">1. PERFORMANCE</div>
                    <div class="moduleHint">/analytics/yahoo/perf-table</div>
                </div>
                {#if perfRows.length}
                    <div class="tableWrap">
                        <table class="kittTable">
                            <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Last</th>
                                {#each periods as p}
                                    <th>{p}</th>
                                {/each}
                                <th>As of</th>
                            </tr>
                            </thead>
                            <tbody>
                            {#each perfRows as row (row.ticker)}
                                <tr>
                                    <td><span class="mono">{row.ticker}</span></td>
                                    <td><span class="mono">{formatNum(row.last)}</span></td>
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
                    <div class="emptyState">No performance data yet.</div>
                {/if}
            </div>

            <!-- ARITHMETIC RETURN -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">2. ARITHMETIC RETURN</div>
                    <div class="moduleHint">/analytics/yahoo/arithmetic-return</div>
                </div>
                {#if arithRows.length}
                    <div class="barsWrap">
                        {#each arithRows as row}
                            <div class="barRow">
                                <div class="barHead">
                                    <div class="ticker mono">{row.ticker}</div>
                                    <div class="value mono" class:negative={row.arithmetic_return < 0}>
                                        {formatPct(row.arithmetic_return)}
                                    </div>
                                </div>
                                <div class="barTrack">
                                    <div class="barFill"
                                         style={`width:${arithBarWidth(row.arithmetic_return, arithMaxAbs)}; background: linear-gradient(90deg, ${row.arithmetic_return < 0 ? '#ff3355' : '#22c55e'}, rgba(255,255,255,0.18));`}>
                                    </div>
                                </div>
                                <div class="barMeta">
                                    <span class="mono">{formatNum(row.start_price, 4)} → {formatNum(row.end_price, 4)}</span>
                                    <span>{row.start_date_used} → {row.end_date_used}</span>
                                </div>
                            </div>
                        {/each}
                    </div>
                {:else}
                    <div class="emptyState">No arithmetic return data yet.</div>
                {/if}
            </div>

            <!-- CUMULATIVE RETURNS -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">3. CUMULATIVE RETURNS</div>
                    <div class="moduleHint">/analytics/yahoo/cumulative-returns</div>
                </div>
                {#if cumSeries.length}
                    <div class="chartsGrid">
                        {#each cumSeries as s, idx (s.ticker)}
                            {@const latest = s.points.length ? s.points[s.points.length - 1] : null}
                            <article class="miniChart">
                                <div class="miniHead">
                                    <span class="ticker mono">{s.ticker}</span>
                                    <span class="badge mono">{formatPctFrac(latest?.cum_return)}</span>
                                </div>
                                <svg viewBox={`0 0 ${CW} ${CH}`} class="cumSvg" preserveAspectRatio="none">
                                    <line x1={CP} x2={CW - CP} y1={CH - CP} y2={CH - CP} class="zeroLine" />
                                    <path d={buildCumPath(s.points)}
                                          fill="none"
                                          stroke={lineColors[idx % lineColors.length]}
                                          stroke-width="2.5"
                                          stroke-linecap="round"
                                          stroke-linejoin="round" />
                                </svg>
                                <div class="miniFoot">
                                    <span class="mono soft">{s.points[0]?.date ?? "—"} → {s.points[s.points.length - 1]?.date ?? "—"}</span>
                                    <span class="mono soft">{s.points.length} pts</span>
                                </div>
                            </article>
                        {/each}
                    </div>
                {:else}
                    <div class="emptyState">No cumulative return data yet.</div>
                {/if}
            </div>

            <!-- DRAWDOWNS -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">4. DRAWDOWNS</div>
                    <div class="moduleHint">/analytics/yahoo/drawdowns</div>
                </div>
                {#if ddRows.length}
                    <div class="chartsGrid">
                        {#each ddRows as row (row.ticker)}
                            <article class="miniChart">
                                <div class="miniHead">
                                    <span class="ticker mono">{row.ticker}</span>
                                    <span class="badge mono redText">{formatPctFrac(row.metrics.max_drawdown)}</span>
                                </div>
                                {#if row.series?.length}
                                    <svg viewBox={`0 0 ${DW} ${DH}`} class="ddSvg" preserveAspectRatio="none">
                                        <path d={buildDDFill(row.series)} class="ddFill" />
                                        <path d={buildDDLine(row.series)} class="ddLine" />
                                    </svg>
                                {:else}
                                    <div class="emptyState">No series.</div>
                                {/if}
                                <div class="miniFoot">
                                    <span class="mono soft">Cur: {formatPctFrac(row.metrics.current_drawdown)}</span>
                                    <span class="mono soft">Episodes: {row.metrics.num_drawdown_episodes}</span>
                                    <span class="mono soft">Avg: {formatNum(row.metrics.avg_drawdown_length_trading_days, 1)}d</span>
                                </div>
                            </article>
                        {/each}
                    </div>
                {:else}
                    <div class="emptyState">No drawdown data yet.</div>
                {/if}
            </div>

            <!-- ANNUALIZED VOLATILITY -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">5. ANNUALIZED VOLATILITY</div>
                    <div class="moduleHint">/analytics/yahoo/annualized-volatility</div>
                </div>
                {#if volRows.length}
                    <div class="barsWrap">
                        {#each volRows as row}
                            <div class="barRow">
                                <div class="barHead">
                                    <div class="ticker mono">{row.ticker}</div>
                                    <div class="value mono">{formatPctFrac(row.annualized_volatility)}</div>
                                </div>
                                <div class="barTrack">
                                    <div class="barFill"
                                         style={`width:${volBarWidth(row.annualized_volatility, volMax)}; background: linear-gradient(90deg, #ff6b35, rgba(255,255,255,0.18));`}>
                                    </div>
                                </div>
                                <div class="barMeta">
                                    <span>{row.frequency} · {row.return_mode}</span>
                                    <span>Period vol: {formatPctFrac(row.volatility_period)}</span>
                                </div>
                            </div>
                        {/each}
                    </div>
                {:else}
                    <div class="emptyState">No volatility data yet.</div>
                {/if}
            </div>

            <!-- VAR / ES -->
            <div class="modulePanel">
                <div class="moduleHead">
                    <div class="panelLabel">6. VAR / ES</div>
                    <div class="moduleHint">/analytics/yahoo/var-es</div>
                </div>
                {#if varEsRows.length}
                    <div class="tableWrap">
                        <table class="kittTable">
                            <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Conf.</th>
                                <th>VaR hist.</th>
                                <th>ES hist.</th>
                                <th>VaR Gauss</th>
                                <th>ES Gauss</th>
                                <th>VaR CF</th>
                                <th>ES CF tail</th>
                            </tr>
                            </thead>
                            <tbody>
                            {#each varEsRows as row, i (row.ticker + "-" + i)}
                                <tr>
                                    <td><span class="mono">{row.ticker}</span></td>
                                    <td><span class="mono">{Math.round(row.confidence_level * 100)}%</span></td>
                                    <td><span class="mono redText">{formatPctFrac(row.var_historical)}</span></td>
                                    <td><span class="mono redText">{formatPctFrac(row.es_historical)}</span></td>
                                    <td><span class="mono">{formatPctFrac(row.var_gaussian)}</span></td>
                                    <td><span class="mono">{formatPctFrac(row.es_gaussian)}</span></td>
                                    <td><span class="mono">{formatPctFrac(row.var_cornish_fisher)}</span></td>
                                    <td><span class="mono">{formatPctFrac(row.es_cf_empirical_tail)}</span></td>
                                </tr>
                            {/each}
                            </tbody>
                        </table>
                    </div>
                {:else}
                    <div class="emptyState">No VaR / ES data yet.</div>
                {/if}
            </div>

            <!-- ERRORS -->
            {#if Object.keys(perfErrors).length || Object.keys(arithErrors).length || Object.keys(cumErrors).length || Object.keys(ddErrors).length || Object.keys(volErrors).length || Object.keys(riskErrors).length}
                <div class="errorsPanel">
                    <div class="errorsTitle">PER-TICKER ERRORS</div>
                    {#each [["perf", perfErrors], ["arith", arithErrors], ["cum", cumErrors], ["dd", ddErrors], ["vol", volErrors], ["var", riskErrors]] as [name, dict]}
                        {#each Object.entries(dict) as [ticker, message]}
                            <div class="errorRow">
                                <span class="mono">[{name}] {ticker}</span>
                                <span>{message}</span>
                            </div>
                        {/each}
                    {/each}
                </div>
            {/if}
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
        color: rgba(255, 255, 255, 0.9);
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
        position: absolute; inset: 0; pointer-events: none;
        background: linear-gradient(180deg, transparent, rgba(255, 0, 60, 0.08), transparent);
        height: 120px; transform: translateY(-120px);
        animation: scan 4.5s linear infinite; opacity: 0.75;
    }
    @keyframes scan { 0% { transform: translateY(-120px); } 100% { transform: translateY(320px); } }

    .header {
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background:
                linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
                linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }
    .headerTop { display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
    .title { margin: 0; font-size: 14px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(255, 0, 60, 0.95); text-shadow: 0 0 12px rgba(255, 0, 60, 0.35); }
    .subtitle { margin-top: 6px; font-size: 12px; color: rgba(235, 235, 245, 0.65); }
    .statusWrap { display: flex; gap: 8px; flex-wrap: wrap; }
    .status, .chip { display: inline-flex; align-items: center; border-radius: 999px; border: 1px solid rgba(255, 0, 60, 0.22); background: rgba(255, 0, 60, 0.10); padding: 5px 10px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }
    .status.soft { background: rgba(255, 0, 60, 0.06); color: rgba(255, 255, 255, 0.74); }
    .chipRow { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
    .chip { color: rgba(235, 235, 245, 0.72); background: rgba(255, 0, 60, 0.07); }

    .body { padding: 16px; display: grid; gap: 16px; }

    .formPanel, .modulePanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 16px;
    }

    .panelLabel {
        font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95); text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
        margin-bottom: 12px;
    }

    .moduleHead {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 10px;
    }
    .moduleHint { font-size: 11px; color: rgba(235, 235, 245, 0.48); font-family: ui-monospace, monospace; margin-bottom: 12px; }

    .formGrid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
    @media (max-width: 1100px) { .formGrid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 700px) { .formGrid { grid-template-columns: 1fr; } }

    .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .field.full { grid-column: 1 / -1; }
    .label { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(235, 235, 245, 0.58); }

    .input {
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.06);
        color: rgba(255, 255, 255, 0.9);
        padding: 10px 12px;
        outline: none;
        width: 100%;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10);
    }
    .input:focus { border-color: rgba(255, 0, 60, 0.55); }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .toggleField { flex-direction: row; align-items: center; gap: 10px; color: rgba(235, 235, 245, 0.82); }

    .errorBox {
        margin-top: 12px; padding: 10px 12px; border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.30); background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 230, 235, 0.95); font-size: 13px;
    }

    .actions { margin-top: 14px; display: flex; justify-content: flex-end; }
    .btn {
        display: inline-flex; align-items: center; justify-content: center;
        padding: 12px 18px; border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.28); background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 255, 255, 0.9);
        font-size: 13px; letter-spacing: 0.06em; cursor: pointer;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10), 0 0 16px rgba(255, 0, 60, 0.10);
        transition: transform 140ms ease, border 140ms ease, box-shadow 140ms ease;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(255, 0, 60, 0.55); }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .moduleStatusRow {
        margin-top: 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }
    .statusPill {
        font-size: 10px;
        letter-spacing: 0.08em;
        padding: 4px 8px;
        border-radius: 999px;
        font-family: ui-monospace, monospace;
        border: 1px solid rgba(255, 255, 255, 0.10);
        background: rgba(255, 255, 255, 0.04);
        color: rgba(235, 235, 245, 0.55);
    }
    .statusPill[data-status="loading"] { color: rgba(255, 204, 51, 0.95); border-color: rgba(255, 204, 51, 0.35); }
    .statusPill[data-status="ok"] { color: rgba(34, 197, 94, 0.95); border-color: rgba(34, 197, 94, 0.35); }
    .statusPill[data-status="error"] { color: rgba(255, 80, 100, 0.95); border-color: rgba(255, 80, 100, 0.35); }

    /* Tables */
    .tableWrap {
        overflow: auto;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
        max-height: 60vh;
    }
    .kittTable {
        width: max-content; min-width: 100%;
        border-collapse: separate; border-spacing: 0;
        background: rgba(0, 0, 0, 0.25);
    }
    .kittTable thead th {
        text-align: left; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
        padding: 12px 14px; border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky; top: 0; z-index: 1; white-space: nowrap;
    }
    .kittTable tbody td {
        padding: 10px 14px; font-size: 13px; color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.08); white-space: nowrap;
    }
    .greenText { color: rgba(34, 197, 94, 0.95); }
    .redText { color: rgba(255, 80, 100, 0.96); }

    /* Bar charts */
    .barsWrap { display: flex; flex-direction: column; gap: 10px; }
    .barRow {
        display: grid; gap: 8px;
        padding: 10px 12px; border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
        background: rgba(0, 0, 0, 0.18);
    }
    .barHead { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .ticker { font-size: 13px; letter-spacing: 0.08em; }
    .value { font-size: 13px; color: rgba(180, 255, 200, 0.96); }
    .value.negative { color: rgba(255, 210, 220, 0.96); }
    .barTrack {
        height: 14px; border-radius: 999px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(0, 0, 0, 0.18));
        border: 1px solid rgba(255, 0, 60, 0.08); overflow: hidden;
    }
    .barFill { height: 100%; border-radius: 999px; box-shadow: 0 0 12px rgba(255, 0, 60, 0.2); }
    .barMeta {
        display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
        font-size: 11px; color: rgba(235, 235, 245, 0.55);
    }

    /* Mini charts (cum + dd) */
    .chartsGrid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
    }
    @media (max-width: 1100px) { .chartsGrid { grid-template-columns: 1fr; } }

    .miniChart {
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: rgba(255, 0, 60, 0.04);
        padding: 12px;
    }
    .miniHead {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 8px;
    }
    .badge {
        font-size: 11px; letter-spacing: 0.08em;
        padding: 4px 10px; border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.08);
    }
    .cumSvg, .ddSvg {
        width: 100%;
        height: 140px;
        display: block;
        border-radius: 10px;
        background: rgba(0, 0, 0, 0.20);
        border: 1px solid rgba(255, 0, 60, 0.10);
    }
    .zeroLine { stroke: rgba(255, 0, 60, 0.28); stroke-width: 1.5; }
    .ddFill { fill: rgba(255, 0, 60, 0.18); }
    .ddLine { fill: none; stroke: rgba(255, 51, 85, 0.85); stroke-width: 2; stroke-linejoin: round; }
    .miniFoot {
        margin-top: 8px;
        display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between;
        font-size: 11px; color: rgba(235, 235, 245, 0.55);
    }
    .soft { color: rgba(235, 235, 245, 0.55); }

    .emptyState {
        color: rgba(235, 235, 245, 0.55); font-size: 13px; padding: 4px 2px;
    }

    .errorsPanel {
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(255, 0, 60, 0.05);
        padding: 12px;
    }
    .errorsTitle {
        font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95); margin-bottom: 10px;
    }
    .errorRow {
        display: flex; gap: 12px; justify-content: space-between;
        padding: 6px 0; border-top: 1px solid rgba(255, 0, 60, 0.08);
        color: rgba(255, 230, 235, 0.9); font-size: 12px;
    }
    .errorRow:first-of-type { border-top: 0; }
</style>
