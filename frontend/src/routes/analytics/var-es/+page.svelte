<script lang="ts">
    import {instance} from "$lib/axiosAPI.js";

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

    type AnnVolRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        start_date_used: string;
        end_date_used: string;
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

    type DrawdownRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        metrics: DrawdownMetrics;
        path: DrawdownPath;
    };

    type RiskPayload<T> = {
        data: T[];
        errors?: Record<string, string>;
    };

    let form = {
        tickers: "AAPL,SPY",
        start_date: "",
        end_date: "",
        auto_adjust: true,
        frequency: "daily",
        return_mode: "arith",
        confidence_levels: "0.95,0.99",
        include_series: false
    };

    let isSubmitting = false;
    let errorMessage = "";

    let drawdowns: DrawdownRow[] = [];
    let annVols: AnnVolRow[] = [];
    let varEsRows: (VaREsPoint & {
        ticker: string;
        observations: number;
        start_date_used: string;
        end_date_used: string
    })[] = [];

    let ddErrors: Record<string, string> = {};
    let volErrors: Record<string, string> = {};
    let riskErrors: Record<string, string> = {};

    function buildTickers(raw: string) {
        return raw.split(",").map((t) => t.trim()).filter(Boolean);
    }

    function formatPct(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${(v * 100).toFixed(2)}%`;
    }

    function formatPct2(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${v.toFixed(2)}%`;
    }

    function formatNum(v: number | null | undefined, dec = 2) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return v.toFixed(dec);
    }

    function riskLevel(currentDd: number, annVol: number, var99: number) {
        const score = Math.abs(currentDd) * 0.45 + annVol * 0.25 + var99 * 0.30;
        if (score >= 0.20) return {label: "HIGH", cls: "riskHigh"};
        if (score >= 0.10) return {label: "MEDIUM", cls: "riskMedium"};
        return {label: "LOW", cls: "riskLow"};
    }

    function worstMetricSummary(dds: DrawdownRow[], vols: AnnVolRow[], risks: typeof varEsRows) {
        const hasAnyData = dds.length > 0 || vols.length > 0 || risks.length > 0;
        if (!hasAnyData) return null;

        return {
            ddWorst: dds.length ? [...dds].sort((a, b) => a.metrics.current_drawdown - b.metrics.current_drawdown)[0] : null,
            volWorst: vols.length ? [...vols].sort((a, b) => b.annualized_volatility - a.annualized_volatility)[0] : null,
            varWorst: risks.length ? [...risks].sort((a, b) => b.var_historical - a.var_historical)[0] : null
        };
    }

    async function submit() {
        errorMessage = "";
        drawdowns = [];
        annVols = [];
        varEsRows = [];
        ddErrors = {};
        volErrors = {};
        riskErrors = {};

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

        const confidence_levels = form.confidence_levels
            .split(",")
            .map((x) => Number(x.trim()))
            .filter((x) => !Number.isNaN(x) && x > 0 && x < 1);

        if (!confidence_levels.length) {
            errorMessage = "Enter at least one valid confidence level, e.g. 0.95,0.99.";
            return;
        }

        isSubmitting = true;
        try {
            const [ddRes, volRes, riskRes] = await Promise.all([
                instance.post<RiskPayload<DrawdownRow>>("/analytics/yahoo/drawdowns", {
                    tickers,
                    start_date: form.start_date,
                    end_date: form.end_date,
                    auto_adjust: form.auto_adjust,
                    include_series: false
                }),
                instance.post<RiskPayload<AnnVolRow>>("/analytics/yahoo/annualized-volatility", {
                    tickers,
                    start_date: form.start_date,
                    end_date: form.end_date,
                    auto_adjust: form.auto_adjust,
                    frequency: form.frequency,
                    return_mode: form.return_mode
                }),
                instance.post<{
                    data: Array<{
                        ticker: string;
                        observations: number;
                        start_date_used: string;
                        end_date_used: string;
                        points: VaREsPoint[];
                    }>;
                    errors?: Record<string, string>;
                }>("/analytics/yahoo/var-es", {
                    tickers,
                    start_date: form.start_date,
                    end_date: form.end_date,
                    auto_adjust: form.auto_adjust,
                    return_mode: form.return_mode,
                    confidence_levels
                })
            ]);

            drawdowns = ddRes.data?.data ?? [];
            annVols = volRes.data?.data ?? [];

            varEsRows = [];
            for (const row of riskRes.data?.data ?? []) {
                for (const pt of row.points ?? []) {
                    varEsRows.push({
                        ticker: row.ticker,
                        observations: row.observations,
                        start_date_used: row.start_date_used,
                        end_date_used: row.end_date_used,
                        ...pt
                    });
                }
            }

            ddErrors = ddRes.data?.errors ?? {};
            volErrors = volRes.data?.errors ?? {};
            riskErrors = riskRes.data?.errors ?? {};
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.response?.data?.message || err?.message || "Unable to load risk data.";
        } finally {
            isSubmitting = false;
        }
    }

    $: summary = worstMetricSummary(drawdowns, annVols, varEsRows);
</script>

<div class="page">
    <section class="card">
        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">RISK MONITOR</h1>
                    <div class="subtitle">Monitor drawdown, volatility, and VaR / ES across multiple tickers.</div>
                </div>
                <div class="statusWrap">
                    <span class="status">ANALYTICS</span>
                    <span class="status soft">Risk dashboard</span>
                </div>
            </div>

            <div class="chipRow">
                <span class="chip">Drawdown</span>
                <span class="chip">Annualized volatility</span>
                <span class="chip">VaR / ES</span>
                <span class="chip">Portfolio watchlist</span>
            </div>
        </header>

        <div class="body">
            <div class="formPanel">
                <div class="panelLabel">INPUTS</div>

                <div class="formGrid">
                    <label class="field full">
                        <span class="label">Tickers</span>
                        <input class="input mono" type="text" bind:value={form.tickers} placeholder="AAPL,SPY,AIR.PA"/>
                    </label>

                    <label class="field">
                        <span class="label">Start date</span>
                        <input class="input mono" type="date" bind:value={form.start_date}/>
                    </label>

                    <label class="field">
                        <span class="label">End date</span>
                        <input class="input mono" type="date" bind:value={form.end_date}/>
                    </label>

                    <label class="field">
                        <span class="label">Frequency</span>
                        <select class="input" bind:value={form.frequency}>
                            <option value="daily">Daily</option>
                            <option value="weekly">Weekly</option>
                            <option value="monthly">Monthly</option>
                        </select>
                    </label>

                    <label class="field">
                        <span class="label">Return mode</span>
                        <select class="input" bind:value={form.return_mode}>
                            <option value="arith">Arithmetic</option>
                            <option value="log">Log</option>
                        </select>
                    </label>

                    <label class="field full">
                        <span class="label">Confidence levels</span>
                        <input class="input mono" type="text" bind:value={form.confidence_levels}
                               placeholder="0.95,0.99"/>
                    </label>

                    <label class="field full toggleField">
                        <input type="checkbox" bind:checked={form.auto_adjust}/>
                        <span>Auto adjust prices</span>
                    </label>
                </div>

                {#if errorMessage}
                    <div class="errorBox">{errorMessage}</div>
                {/if}

                <div class="actions">
                    <button class="btn" type="button" on:click={submit} disabled={isSubmitting}>
                        {isSubmitting ? "Running…" : "Run risk monitor"}
                    </button>
                </div>
            </div>

            <div class="resultsPanel">
                <div class="panelLabel">SUMMARY</div>

                {#if summary}
                    <div class="summaryRow">
                        <div class="summaryCard">
                            <div class="summaryK">Tickers</div>
                            <div class="summaryV">{drawdowns.length || annVols.length || varEsRows.length}</div>
                        </div>

                        <div class="summaryCard">
                            <div class="summaryK">Worst current DD</div>
                            <div class="summaryV redText">{summary.ddWorst ? formatPct(summary.ddWorst.metrics.current_drawdown) : "—"}</div>
                        </div>

                        <div class="summaryCard">
                            <div class="summaryK">Highest ann. vol</div>
                            <div class="summaryV amberText">
                                {summary.volWorst ? formatPct2(summary.volWorst.annualized_volatility * 100) : "—"}
                            </div>
                        </div>

                        <div class="summaryCard">
                            <div class="summaryK">Worst historical VaR</div>
                            <div class="summaryV redText">
                                {summary.varWorst ? formatPct2(summary.varWorst.var_historical * 100) : "—"}
                            </div>
                        </div>
                    </div>
                {:else}
                    <div class="emptyState">No risk snapshot yet. Fill the form and run the monitor.</div>
                {/if}

                <div class="sectionBlock">
                    <div class="sectionTitle">DRAWDOWNS</div>
                    {#if drawdowns.length}
                        <div class="tableWrap">
                            <table class="kittTable">
                                <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Current DD</th>
                                    <th>Max DD</th>
                                    <th>Episodes</th>
                                    <th>Avg days</th>
                                    <th>Trough</th>
                                    <th>Recovery</th>
                                </tr>
                                </thead>
                                <tbody>
                                {#each drawdowns as row (row.ticker)}
                                    <tr>
                                        <td><span class="mono">{row.ticker}</span></td>
                                        <td><span class="mono redText">{formatPct(row.metrics.current_drawdown)}</span>
                                        </td>
                                        <td><span class="mono redText">{formatPct(row.metrics.max_drawdown)}</span></td>
                                        <td><span class="mono">{row.metrics.num_drawdown_episodes}</span></td>
                                        <td><span
                                                class="mono">{formatNum(row.metrics.avg_drawdown_length_trading_days)}</span>
                                        </td>
                                        <td><span class="mono">{row.path.trough_date}</span></td>
                                        <td><span class="mono">{row.path.recovery_date ?? "—"}</span></td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else}
                        <div class="emptyState">No drawdown data yet.</div>
                    {/if}
                </div>

                <div class="sectionBlock">
                    <div class="sectionTitle">ANNUALIZED VOLATILITY</div>
                    {#if annVols.length}
                        <div class="tableWrap">
                            <table class="kittTable">
                                <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Vol period</th>
                                    <th>Annualized vol</th>
                                    <th>Frequency</th>
                                    <th>Return mode</th>
                                    <th>Used start</th>
                                    <th>Used end</th>
                                </tr>
                                </thead>
                                <tbody>
                                {#each annVols as row (row.ticker)}
                                    <tr>
                                        <td><span class="mono">{row.ticker}</span></td>
                                        <td><span class="mono">{formatPct2(row.volatility_period * 100)}</span></td>
                                        <td><span
                                                class="mono amberText">{formatPct2(row.annualized_volatility * 100)}</span>
                                        </td>
                                        <td><span class="mono">{row.frequency}</span></td>
                                        <td><span class="mono">{row.return_mode}</span></td>
                                        <td><span class="mono">{row.start_date_used}</span></td>
                                        <td><span class="mono">{row.end_date_used}</span></td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else}
                        <div class="emptyState">No volatility data yet.</div>
                    {/if}
                </div>

                <div class="sectionBlock">
                    <div class="sectionTitle">VAR / ES</div>
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
                                        <td><span class="mono redText">{formatPct2(row.var_historical * 100)}</span>
                                        </td>
                                        <td><span class="mono redText">{formatPct2(row.es_historical * 100)}</span></td>
                                        <td><span class="mono">{formatPct2(row.var_gaussian * 100)}</span></td>
                                        <td><span class="mono">{formatPct2(row.es_gaussian * 100)}</span></td>
                                        <td><span class="mono">{formatPct2(row.var_cornish_fisher * 100)}</span></td>
                                        <td><span class="mono">{formatPct2(row.es_cf_empirical_tail * 100)}</span></td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else}
                        <div class="emptyState">No VaR / ES data yet.</div>
                    {/if}
                </div>

                {#if Object.keys(ddErrors).length > 0 || Object.keys(volErrors).length > 0 || Object.keys(riskErrors).length > 0}
                    <div class="errorsPanel">
                        <div class="errorsTitle">ERRORS</div>

                        {#each Object.entries(ddErrors) as [ticker, message]}
                            <div class="errorRow">
                                <span class="mono">{ticker}</span>
                                <span>{message}</span>
                            </div>
                        {/each}

                        {#each Object.entries(volErrors) as [ticker, message]}
                            <div class="errorRow">
                                <span class="mono">{ticker}</span>
                                <span>{message}</span>
                            </div>
                        {/each}

                        {#each Object.entries(riskErrors) as [ticker, message]}
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
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        background: radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
        linear-gradient(180deg, #07080c, #04040a);
    }

    .card {
        width: min(1500px, 100%);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
        border: 1px solid rgba(255, 0, 60, 0.22);
        overflow: hidden;
        color: rgba(255, 255, 255, 0.9);
    }

    .header {
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background: linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
        linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }

    .headerTop {
        display: flex;
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
    }

    .status, .chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.10);
        padding: 6px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
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

    .body {
        padding: 16px;
        display: grid;
        gap: 16px;
    }

    .formPanel, .resultsPanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 16px;
    }

    .panelLabel, .sectionTitle, .errorsTitle {
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        margin-bottom: 12px;
    }

    .sectionBlock {
        margin-top: 18px;
    }

    .formGrid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
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
        color: rgba(255, 255, 255, 0.92);
        padding: 10px 12px;
        outline: none;
        width: 100%;
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    .toggleField {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 10px;
        color: rgba(235, 235, 245, 0.82);
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
        cursor: pointer;
    }

    .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
    }

    .summaryRow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 14px;
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
    }

    .redText {
        color: rgba(255, 80, 100, 0.96);
    }

    .amberText {
        color: rgba(255, 190, 70, 0.96);
    }

    .riskLow {
        color: rgba(34, 197, 94, 0.95);
    }

    .riskMedium {
        color: rgba(255, 190, 70, 0.96);
    }

    .riskHigh {
        color: rgba(255, 80, 100, 0.96);
    }

    .tableWrap {
        overflow: auto;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
    }

    .kittTable {
        width: 100%;
        border-collapse: collapse;
        min-width: 1000px;
        background: rgba(0, 0, 0, 0.18);
    }

    .kittTable th,
    .kittTable td {
        padding: 0.8rem 0.9rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        white-space: nowrap;
        text-align: left;
    }

    .kittTable th {
        position: sticky;
        top: 0;
        background: rgba(20, 20, 30, 0.98);
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }

    .emptyState {
        color: rgba(235, 235, 245, 0.62);
        padding: 4px 0;
        font-size: 13px;
    }

    .errorsPanel {
        margin-top: 14px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(255, 0, 60, 0.05);
        padding: 12px;
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

    @media (max-width: 900px) {
        .formGrid,
        .summaryRow {
            grid-template-columns: 1fr;
        }
    }
</style>