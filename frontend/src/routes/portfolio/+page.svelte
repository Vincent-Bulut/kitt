<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";
    import { onMount } from "svelte";
    import { page } from "$app/stores";

    type Portfolio = { id: number; name: string };
    type Asset = { symbol: string; name: string; isin: string; currency: string };

    type Transaction = {
        id: number;
        portfolio_id: number;
        symbol: string;
        date: string;
        side: "BUY" | "SELL";
        quantity: number;
        price: number;
        transaction_fee: number | null;
        amount: number | null;
        currency: string | null;
    };

    type PositionRow = {
        symbol: string;
        name: string | null;
        currency: string | null;
        current_qty: number;
        avg_cost: number | null;
        cost_basis: number;
        market_price: number | null;
        market_value: number | null;
        weight: number | null;
        realized_pnl: number;
        unrealized_pnl: number | null;
        total_pnl: number | null;
        total_fees: number;
        estimated_ter_cost_annual: number | null;
        contribution_to_portfolio_pnl: number | null;
        num_transactions: number;
        price_error: string | null;
    };

    type PositionView = {
        portfolio_id: number;
        portfolio_name: string;
        asof_used: string | null;
        total_market_value: number;
        total_cost_basis: number;
        total_realized_pnl: number;
        total_unrealized_pnl: number;
        total_pnl: number;
        total_fees: number;
        estimated_ter_cost_annual: number;
        rows: PositionRow[];
    };

    type PerfRow = {
        ticker: string;
        asof_requested: string | null;
        asof_used: string;
        last: number;
        perf: Record<string, number | null>;
    };

    type AnnVolRow = {
        ticker: string;
        annualized_volatility: number;
    };

    type DrawdownPoint = {
        date: string;
        price: number;
        running_max: number;
        drawdown: number;
    };

    type DrawdownEpisode = {
        start_date: string;
        trough_date: string;
        end_date: string | null;
        duration_days: number;
        max_drawdown: number;
    };

    type DrawdownRow = {
        ticker: string;
        metrics: {
            max_drawdown: number;
            current_drawdown: number;
            num_drawdown_episodes: number;
            avg_drawdown_length_trading_days: number;
            max_drawdown_length_trading_days: number;
            worst_episode_trough: number;
        };
        episodes: DrawdownEpisode[];
        series?: DrawdownPoint[];
    };

    type CumReturnPoint = {
        date: string;
        cum_return: number;
    };

    type CumReturnSeries = {
        ticker: string;
        points: CumReturnPoint[];
    };

    type AllMetricsResponse = {
        perf?: { data: PerfRow[] };
        vol?: { data: AnnVolRow[] };
        dd?: { data: DrawdownRow[] };
        risk?: { data: VaREsRow[] };
        cum_returns?: { data: CumReturnSeries[] };
    };

    let portfolios: Portfolio[] = [];
    let assets: Asset[] = [];
    let selectedPortfolioId: number | null = null;

    let transactions: Transaction[] = [];
    let positionView: PositionView | null = null;

    let isLoadingPortfolios = false;
    let isLoadingData = false;
    let isCreating = false;
    let isDeletingId: number | null = null;

    let errorMessage = "";
    let formError = "";
    let formOk = "";

    let view: "log" | "positions" | "analytics" = "positions";

    let analyticsRows: PerfRow[] = [];
    let volRows: AnnVolRow[] = [];
    let ddRows: DrawdownRow[] = [];
    let riskRows: VaREsRow[] = [];
    let cumReturnsRows: CumReturnSeries[] = [];
    let isFetchingAnalytics = false;
    let analyticsError = "";
    let confidenceLevels = "0.95";
    let selectedPeriod = "3Y";

    let form = {
        symbol: "",
        date: "",
        side: "BUY" as "BUY" | "SELL",
        quantity: "",
        price: "",
        transaction_fee: "",
        amount: "",
        currency: ""
    };

    let feeManuallyEdited = false;

    function computeFee(montant: number): number {
        const raw = montant < 7750 ? 16.65 : montant * 0.0022;
        return Math.round(raw * 100) / 100;
    }

    $: if (!feeManuallyEdited) {
        const q = Number(form.quantity);
        const p = Number(form.price);
        const a = Number(form.amount);
        const montant =
            Number.isFinite(a) && a > 0
                ? a
                : Number.isFinite(q) && Number.isFinite(p) && q > 0 && p > 0
                ? q * p
                : 0;
        if (montant > 0) {
            const next = computeFee(montant);
            if (form.transaction_fee !== next) form.transaction_fee = next as any;
        }
    }

    async function loadPortfolios() {
        isLoadingPortfolios = true;
        errorMessage = "";
        try {
            const res = await instance.get<Portfolio[]>("/admin/portfolios");
            portfolios = res.data ?? [];
            if (portfolios.length > 0 && selectedPortfolioId === null) {
                selectedPortfolioId = portfolios[0].id;
            }
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.message || "Unable to load portfolios.";
        } finally {
            isLoadingPortfolios = false;
        }
    }

    async function loadAssets() {
        try {
            const res = await instance.get<Asset[]>("/referential/assets");
            assets = res.data ?? [];
        } catch (err) {
            // non-blocking
            console.error("Unable to load assets:", err);
        }
    }

    async function loadData() {
        if (selectedPortfolioId === null) return;
        isLoadingData = true;
        errorMessage = "";
        try {
            const [txRes, posRes] = await Promise.all([
                instance.get<Transaction[]>(`/portfolios/${selectedPortfolioId}/transactions`),
                instance.get<PositionView>(`/portfolios/${selectedPortfolioId}/positions-view`)
            ]);
            transactions = txRes.data ?? [];
            positionView = posRes.data;

            if (view === "analytics") {
                loadAnalytics();
            }
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.message || "Unable to load portfolio data.";
        } finally {
            isLoadingData = false;
        }
    }

    async function loadAnalytics() {
        if (!positionView || positionView.rows.length === 0) {
            analyticsRows = [];
            volRows = [];
            ddRows = [];
            riskRows = [];
            cumReturnsRows = [];
            return;
        }
        isFetchingAnalytics = true;
        analyticsError = "";
        try {
            const tickers = positionView.rows.map(r => r.symbol);
            const payload = {
                tickers,
                asof: positionView.asof_used || null,
                period: selectedPeriod,
                auto_adjust: true,
                frequency: "daily",
                confidence_levels: confidenceLevels
            };
            const res = await instance.post<AllMetricsResponse>("/analytics/yahoo/all-metrics", payload);
            analyticsRows = res.data?.perf?.data ?? [];
            volRows = res.data?.vol?.data ?? [];
            ddRows = res.data?.dd?.data ?? [];
            riskRows = res.data?.risk?.data ?? [];
            cumReturnsRows = res.data?.cum_returns?.data ?? [];
        } catch (err: any) {
            analyticsError = err?.response?.data?.detail || err?.message || "Unable to load analytics.";
        } finally {
            isFetchingAnalytics = false;
        }
    }

    $: if (view === "analytics" && positionView && analyticsRows.length === 0 && !isFetchingAnalytics) {
        loadAnalytics();
    }

    async function createTransaction() {
        formError = "";
        formOk = "";

        if (selectedPortfolioId === null) {
            formError = "Select a portfolio first.";
            return;
        }
        if (!form.symbol.trim()) {
            formError = "Symbol is required.";
            return;
        }
        if (!form.date) {
            formError = "Date is required.";
            return;
        }
        const qty = parseFloat(form.quantity);
        const price = parseFloat(form.price);
        if (!Number.isFinite(qty) || qty <= 0) {
            formError = "Quantity must be > 0.";
            return;
        }
        if (!Number.isFinite(price) || price < 0) {
            formError = "Price must be >= 0.";
            return;
        }

        const payload: Record<string, any> = {
            symbol: form.symbol.trim(),
            date: form.date,
            side: form.side,
            quantity: qty,
            price: price
        };
        if (form.transaction_fee !== "" && form.transaction_fee != null) {
            const fee = Number(form.transaction_fee);
            if (Number.isFinite(fee)) payload.transaction_fee = fee;
        }
        if (form.amount !== "" && form.amount != null) {
            const amt = Number(form.amount);
            if (Number.isFinite(amt)) payload.amount = amt;
        }
        if (form.currency.trim()) payload.currency = form.currency.trim().toUpperCase();

        isCreating = true;
        try {
            await instance.post(`/portfolios/${selectedPortfolioId}/transactions`, payload);
            formOk = `Transaction created (${form.side} ${qty} ${form.symbol})`;
            form.quantity = "";
            form.price = "";
            form.transaction_fee = "";
            form.amount = "";
            feeManuallyEdited = false;
            await loadData();
        } catch (err: any) {
            formError = err?.response?.data?.detail || err?.message || "Unable to create transaction.";
        } finally {
            isCreating = false;
        }
    }

    async function deleteTransaction(id: number) {
        if (!confirm("Delete this transaction? Position metrics will be recomputed.")) return;
        isDeletingId = id;
        try {
            await instance.delete(`/transactions/${id}`);
            await loadData();
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.message || "Unable to delete transaction.";
        } finally {
            isDeletingId = null;
        }
    }

    function formatPctPerf(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${v.toFixed(2)}%`;
    }

    function formatPct(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return `${(v * 100).toFixed(2)}%`;
    }

    function formatNum(v: number | null | undefined, dec = 2) {
        if (v === null || v === undefined || Number.isNaN(v)) return "—";
        return v.toFixed(dec);
    }

    function pnlClass(v: number | null | undefined) {
        if (v === null || v === undefined || Number.isNaN(v)) return "";
        if (v > 0) return "greenText";
        if (v < 0) return "redText";
        return "";
    }

    // SVG Helpers
    const CHART_W = 360;
    const CHART_H = 100;
    const CHART_PAD = { top: 10, right: 10, bottom: 20, left: 40 };

    function buildLinePath(points: { x: number; y: number }[]) {
        if (points.length < 2) return "";
        return `M ${points[0].x} ${points[0].y} ` + points.slice(1).map(p => `L ${p.x} ${p.y}`).join(" ");
    }

    function buildAreaPath(points: { x: number; y: number }[], baselineY: number) {
        if (points.length < 2) return "";
        const line = buildLinePath(points);
        return `${line} L ${points[points.length - 1].x} ${baselineY} L ${points[0].x} ${baselineY} Z`;
    }

    function getCumReturnsChartData(series: CumReturnSeries) {
        const pts = series.points;
        if (!pts || pts.length === 0) return null;

        const minVal = Math.min(...pts.map(p => p.cum_return));
        const maxVal = Math.max(...pts.map(p => p.cum_return));
        const range = maxVal - minVal || 0.1;
        
        const chartPoints = pts.map((p, i) => ({
            x: CHART_PAD.left + (i / (pts.length - 1)) * (CHART_W - CHART_PAD.left - CHART_PAD.right),
            y: CHART_H - CHART_PAD.bottom - ((p.cum_return - minVal) / range) * (CHART_H - CHART_PAD.top - CHART_PAD.bottom)
        }));

        const baselineVal = 0;
        const baselineY = CHART_H - CHART_PAD.bottom - ((baselineVal - minVal) / range) * (CHART_H - CHART_PAD.top - CHART_PAD.bottom);

        return {
            path: buildLinePath(chartPoints),
            area: buildAreaPath(chartPoints, CHART_H - CHART_PAD.bottom),
            minVal,
            maxVal,
            baselineY,
            lastVal: pts[pts.length-1].cum_return
        };
    }

    function getDrawdownChartData(points: DrawdownPoint[] | undefined) {
        if (!points || points.length === 0) return null;

        const minDD = Math.min(...points.map(p => p.drawdown)); // Drawdown est négatif
        const maxVal = 0;
        const minVal = minDD < -0.01 ? minDD : -0.1;
        const range = maxVal - minVal;

        const chartPoints = points.map((p, i) => ({
            x: CHART_PAD.left + (i / (points.length - 1)) * (CHART_W - CHART_PAD.left - CHART_PAD.right),
            y: CHART_H - CHART_PAD.bottom - ((p.drawdown - minVal) / range) * (CHART_H - CHART_PAD.top - CHART_PAD.bottom)
        }));

        return {
            path: buildLinePath(chartPoints),
            area: buildAreaPath(chartPoints, CHART_H - CHART_PAD.bottom - ((-minVal / range) * (CHART_H - CHART_PAD.top - CHART_PAD.bottom))),
            minVal,
            maxVal,
            baselineY: CHART_H - CHART_PAD.bottom - ((0 - minVal) / range) * (CHART_H - CHART_PAD.top - CHART_PAD.bottom)
        };
    }

    onMount(async () => {
        const idFromUrl = $page.url.searchParams.get("id");
        if (idFromUrl) {
            const parsed = parseInt(idFromUrl, 10);
            if (Number.isFinite(parsed)) selectedPortfolioId = parsed;
        }
        await Promise.all([loadPortfolios(), loadAssets()]);
        if (selectedPortfolioId !== null) await loadData();
    });

    $: if (selectedPortfolioId !== null) {
        loadData();
    }
</script>

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">POSITIONS COCKPIT</h1>
                    <div class="subtitle">
                        Log new trades, browse history and inspect derived positions per portfolio.
                    </div>
                </div>
                <div class="statusWrap">
                    <span class="status soft">Yahoo prices</span>
                </div>
            </div>
            <div class="chipRow">
                <span class="chip">Buy / Sell</span>
                <span class="chip">Weights</span>
            </div>
        </header>

        <div class="body">
            <!-- Portfolio + view switcher -->
            <div class="topBar">
                <label class="field">
                    <span class="label">Portfolio</span>
                    <select class="input" bind:value={selectedPortfolioId} disabled={isLoadingPortfolios || portfolios.length === 0}>
                        {#if portfolios.length === 0}
                            <option value={null}>No portfolios — create one in /admin</option>
                        {:else}
                            {#each portfolios as p}
                                <option value={p.id}>{p.name}</option>
                            {/each}
                        {/if}
                    </select>
                </label>

                <div class="viewSwitch">
                    <button class="switchBtn" class:active={view === "positions"} on:click={() => (view = "positions")}>
                        Positions view
                    </button>
                    <button class="switchBtn" class:active={view === "analytics"} on:click={() => (view = "analytics")}>
                        Analytics
                    </button>
                    <button class="switchBtn" class:active={view === "log"} on:click={() => (view = "log")}>
                        Transactions log
                    </button>
                </div>
            </div>

            {#if errorMessage}
                <div class="errorBox">{errorMessage}</div>
            {/if}

            <!-- New transaction form -->
            <details class="formCard">
                <summary>
                    <span class="panelLabel">+ NEW TRANSACTION</span>
                </summary>

                <div class="formGrid">
                    <label class="field">
                        <span class="label">Symbol</span>
                        <input class="input mono" type="text" list="assetList" bind:value={form.symbol} placeholder="AAPL" />
                        <datalist id="assetList">
                            {#each assets as a}
                                <option value={a.symbol}>{a.name}</option>
                            {/each}
                        </datalist>
                    </label>
                    <label class="field">
                        <span class="label">Date</span>
                        <input class="input mono" type="date" bind:value={form.date} />
                    </label>
                    <label class="field">
                        <span class="label">Side</span>
                        <select class="input" bind:value={form.side}>
                            <option value="BUY">BUY</option>
                            <option value="SELL">SELL</option>
                        </select>
                    </label>
                    <label class="field">
                        <span class="label">Quantity</span>
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.quantity} placeholder="10" />
                    </label>
                    <label class="field">
                        <span class="label">Price</span>
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.price} placeholder="180.50" />
                    </label>
                    <label class="field">
                        <span class="label">Transaction fee</span>
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.transaction_fee} on:input={() => (feeManuallyEdited = true)} placeholder="auto" />
                    </label>
                    <label class="field">
                        <span class="label">Amount (optional)</span>
                        <input class="input mono" type="number" step="any" bind:value={form.amount} placeholder="auto = qty × price" />
                    </label>
                    <label class="field">
                        <span class="label">Currency (optional)</span>
                        <input class="input mono" type="text" maxlength="3" bind:value={form.currency} placeholder="EUR" />
                    </label>
                </div>

                {#if formError}
                    <div class="errorBox">{formError}</div>
                {/if}
                {#if formOk}
                    <div class="okBox">{formOk}</div>
                {/if}

                <div class="actions">
                    <button class="btn primary" type="button" on:click={createTransaction} disabled={isCreating || selectedPortfolioId === null}>
                        {isCreating ? "Creating…" : "Create transaction"}
                    </button>
                </div>
            </details>

            <!-- POSITIONS VIEW -->
            {#if view === "positions"}
                <div class="modulePanel">
                    <div class="moduleHead">
                        <div class="panelLabel">POSITIONS VIEW</div>
                        <div class="moduleHint">/portfolios/{selectedPortfolioId}/positions-view</div>
                    </div>

                    {#if positionView && positionView.rows.length > 0}
                        <div class="kpiRow">
                            <div class="kpiCard">
                                <div class="kpiK">Market value</div>
                                <div class="kpiV mono">{formatNum(positionView.total_market_value)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Cost basis</div>
                                <div class="kpiV mono">{formatNum(positionView.total_cost_basis)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Realized P&amp;L</div>
                                <div class="kpiV mono {pnlClass(positionView.total_realized_pnl)}">{formatNum(positionView.total_realized_pnl)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Unrealized P&amp;L</div>
                                <div class="kpiV mono {pnlClass(positionView.total_unrealized_pnl)}">{formatNum(positionView.total_unrealized_pnl)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Total P&amp;L</div>
                                <div class="kpiV mono {pnlClass(positionView.total_pnl)}">{formatNum(positionView.total_pnl)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Total fees</div>
                                <div class="kpiV mono">{formatNum(positionView.total_fees)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">Est. TER / yr</div>
                                <div class="kpiV mono">{formatNum(positionView.estimated_ter_cost_annual)}</div>
                            </div>
                            <div class="kpiCard">
                                <div class="kpiK">As of</div>
                                <div class="kpiV mono">{positionView.asof_used ?? "—"}</div>
                            </div>
                        </div>

                        <div class="tableWrap">
                            <table class="kittTable">
                                <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Name</th>
                                    <th>Ccy</th>
                                    <th>Qty</th>
                                    <th>Avg cost</th>
                                    <th>Cost basis</th>
                                    <th>Price</th>
                                    <th>Market value</th>
                                    <th>Weight</th>
                                    <th>Realized P&amp;L</th>
                                    <th>Unrealized P&amp;L</th>
                                    <th>Total P&amp;L</th>
                                    <th>Fees</th>
                                    <th>TER / yr</th>
                                    <th>Contrib.</th>
                                    <th>Tx</th>
                                </tr>
                                </thead>
                                <tbody>
                                {#each positionView.rows as row (row.symbol)}
                                    <tr>
                                        <td><span class="mono">{row.symbol}</span></td>
                                        <td class="nameCell" title={row.name ?? ""}>{row.name ?? "—"}</td>
                                        <td><span class="mono">{row.currency ?? "—"}</span></td>
                                        <td><span class="mono">{formatNum(row.current_qty, 4)}</span></td>
                                        <td><span class="mono">{formatNum(row.avg_cost, 4)}</span></td>
                                        <td><span class="mono">{formatNum(row.cost_basis)}</span></td>
                                        <td>
                                            {#if row.price_error}
                                                <span class="redText" title={row.price_error}>err</span>
                                            {:else}
                                                <span class="mono">{formatNum(row.market_price, 4)}</span>
                                            {/if}
                                        </td>
                                        <td><span class="mono">{formatNum(row.market_value)}</span></td>
                                        <td><span class="mono">{formatPct(row.weight)}</span></td>
                                        <td><span class="mono {pnlClass(row.realized_pnl)}">{formatNum(row.realized_pnl)}</span></td>
                                        <td><span class="mono {pnlClass(row.unrealized_pnl)}">{formatNum(row.unrealized_pnl)}</span></td>
                                        <td><span class="mono {pnlClass(row.total_pnl)}">{formatNum(row.total_pnl)}</span></td>
                                        <td><span class="mono">{formatNum(row.total_fees)}</span></td>
                                        <td><span class="mono">{formatNum(row.estimated_ter_cost_annual)}</span></td>
                                        <td><span class="mono">{formatPct(row.contribution_to_portfolio_pnl)}</span></td>
                                        <td><span class="mono soft">{row.num_transactions}</span></td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else if isLoadingData}
                        <div class="emptyState">Loading positions…</div>
                    {:else}
                        <div class="emptyState">No transactions yet for this portfolio.</div>
                    {/if}
                </div>
            {/if}

            <!-- ANALYTICS VIEW -->
            {#if view === "analytics"}
                <div class="modulePanel">
                    <div class="moduleHead">
                        <div class="panelLabel">ASSETS ANALYTICS</div>
                        <div class="moduleHint">Yahoo Finance comprehensive metrics</div>
                    </div>

                    <div class="analyticsSettings">
                        <label class="field inlineField">
                            <span class="label">VaR Confidence Levels</span>
                            <div class="inputGroup">
                                <input class="input mono xsmallInput" type="text" bind:value={confidenceLevels} placeholder="0.95, 0.99" />
                                <button class="btn primary xsmall" on:click={loadAnalytics} disabled={isFetchingAnalytics}>Update</button>
                            </div>
                        </label>
                        <label class="field inlineField">
                            <span class="label">Period</span>
                            <select class="input mono xsmallInput" bind:value={selectedPeriod} on:change={loadAnalytics} disabled={isFetchingAnalytics}>
                                <option value="1M">1 Month</option>
                                <option value="3M">3 Months</option>
                                <option value="6M">6 Months</option>
                                <option value="1Y">1 Year</option>
                                <option value="2Y">2 Years</option>
                                <option value="3Y">3 Years</option>
                                <option value="5Y">5 Years</option>
                                <option value="10Y">10 Years</option>
                            </select>
                        </label>
                    </div>

                    {#if analyticsError}
                        <div class="errorBox">{analyticsError}</div>
                    {/if}

                    {#if isFetchingAnalytics}
                        <div class="emptyState">Fetching analytics data…</div>
                    {:else}
                        <div class="sectionTitle">Performance</div>
                        <div class="tableWrap">
                            <table class="kittTable">
                                <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Last</th>
                                    <th>1D</th>
                                    <th>1W</th>
                                    <th>1M</th>
                                    <th>YTD</th>
                                    <th>1Y</th>
                                    <th>3Y</th>
                                    <th>5Y</th>
                                    <th>As of</th>
                                </tr>
                                </thead>
                                <tbody>
                                {#each analyticsRows as row (row.ticker)}
                                    <tr>
                                        <td><span class="mono">{row.ticker}</span></td>
                                        <td><span class="mono">{formatNum(row.last, 2)}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['1D'])}">{formatPctPerf(row.perf['1D'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['1W'])}">{formatPctPerf(row.perf['1W'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['1M'])}">{formatPctPerf(row.perf['1M'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['YTD'])}">{formatPctPerf(row.perf['YTD'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['1Y'])}">{formatPctPerf(row.perf['1Y'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['3Y'])}">{formatPctPerf(row.perf['3Y'])}</span></td>
                                        <td><span class="mono {pnlClass(row.perf['5Y'])}">{formatPctPerf(row.perf['5Y'])}</span></td>
                                        <td><span class="mono soft">{row.asof_used}</span></td>
                                    </tr>
                                {:else}
                                    <tr>
                                        <td colspan="10" class="emptyState">No performance data found.</td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>

                        <div class="grid2">
                            <div>
                                <div class="sectionTitle">Risk & Volatility</div>
                                <div class="tableWrap">
                                    <table class="kittTable">
                                        <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Ann. Vol</th>
                                            <th>Conf.</th>
                                            <th>VaR</th>
                                            <th>ES</th>
                                        </tr>
                                        </thead>
                                        <tbody>
                                        {#each volRows as vol}
                                            {@const risk = riskRows.find(r => r.ticker === vol.ticker)}
                                            {#if risk && risk.points.length > 0}
                                                {#each risk.points as pt, i}
                                                    <tr>
                                                        {#if i === 0}
                                                            <td rowspan={risk.points.length}><span class="mono">{vol.ticker}</span></td>
                                                            <td rowspan={risk.points.length}><span class="mono">{formatPct(vol.annualized_volatility)}</span></td>
                                                        {/if}
                                                        <td><span class="mono soft">{(pt.confidence_level * 100).toFixed(0)}%</span></td>
                                                        <td><span class="mono">{formatPct(pt.var_historical)}</span></td>
                                                        <td><span class="mono">{formatPct(pt.es_historical)}</span></td>
                                                    </tr>
                                                {/each}
                                            {:else}
                                                <tr>
                                                    <td><span class="mono">{vol.ticker}</span></td>
                                                    <td><span class="mono">{formatPct(vol.annualized_volatility)}</span></td>
                                                    <td colspan="3" class="soft">No risk data</td>
                                                </tr>
                                            {/if}
                                        {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            <div>
                                <div class="sectionTitle">Drawdowns</div>
                                <div class="tableWrap">
                                    <table class="kittTable">
                                        <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Max DD</th>
                                            <th>Current DD</th>
                                        </tr>
                                        </thead>
                                        <tbody>
                                        {#each ddRows as dd}
                                            <tr>
                                                <td><span class="mono">{dd.ticker}</span></td>
                                                <td><span class="mono redText">{formatPct(dd.metrics.max_drawdown)}</span></td>
                                                <td><span class="mono {pnlClass(-dd.metrics.current_drawdown)}">{formatPct(dd.metrics.current_drawdown)}</span></td>
                                            </tr>
                                        {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>

                        <div class="sectionTitle">Cumulative Returns Charts</div>
                        <div class="chartGrid">
                            {#each cumReturnsRows as series}
                                {@const crData = getCumReturnsChartData(series)}
                                <div class="chartCard">
                                    <div class="chartHeader">
                                        <span class="mono bold">{series.ticker}</span>
                                        {#if crData}
                                            <span class="mono {pnlClass(crData.lastVal)}">{formatPct(crData.lastVal)}</span>
                                        {/if}
                                    </div>
                                    <div class="chartWrap">
                                        {#if crData}
                                            <svg viewBox="0 0 {CHART_W} {CHART_H}" class="miniChart">
                                                <defs>
                                                    <linearGradient id="grad-cr-{series.ticker}" x1="0" y1="0" x2="0" y2="1">
                                                        <stop offset="0%" stop-color="rgba(0, 212, 255, 0.2)" />
                                                        <stop offset="100%" stop-color="rgba(0, 212, 255, 0)" />
                                                    </linearGradient>
                                                </defs>
                                                <line x1={CHART_PAD.left} y1={crData.baselineY} x2={CHART_W - CHART_PAD.right} y2={crData.baselineY} stroke="rgba(255,255,255,0.1)" />
                                                <path d={crData.area} fill="url(#grad-cr-{series.ticker})" />
                                                <path d={crData.path} fill="none" stroke="rgba(0, 212, 255, 0.8)" stroke-width="1.5" />
                                                <text x="5" y="15" fill="rgba(255,255,255,0.4)" font-size="9">{formatPct(crData.maxVal)}</text>
                                                <text x="5" y={CHART_H - CHART_PAD.bottom} fill="rgba(255,255,255,0.4)" font-size="9">{formatPct(crData.minVal)}</text>
                                            </svg>
                                        {:else}
                                            <div class="emptyState xsmall">No return data</div>
                                        {/if}
                                    </div>
                                </div>
                            {/each}
                        </div>

                        <div class="sectionTitle">Drawdown Charts</div>
                        <div class="chartGrid">
                            {#each ddRows as dd}
                                {@const ddData = getDrawdownChartData(dd.series)}
                                <div class="chartCard">
                                    <div class="chartHeader">
                                        <span class="mono bold">{dd.ticker}</span>
                                        <span class="mono redText">{formatPct(dd.metrics.max_drawdown)}</span>
                                    </div>
                                    <div class="chartWrap">
                                        {#if ddData}
                                            <svg viewBox="0 0 {CHART_W} {CHART_H}" class="miniChart">
                                                <line x1={CHART_PAD.left} y1={ddData.baselineY} x2={CHART_W - CHART_PAD.right} y2={ddData.baselineY} stroke="rgba(255,255,255,0.1)" />
                                                <path d={ddData.area} fill="rgba(255, 69, 58, 0.1)" />
                                                <path d={ddData.path} fill="none" stroke="rgba(255, 69, 58, 0.6)" stroke-width="1.2" />
                                                <text x="5" y={CHART_H - CHART_PAD.bottom} fill="rgba(255,255,255,0.4)" font-size="9">{formatPct(ddData.minVal)}</text>
                                                <text x="5" y="15" fill="rgba(255,255,255,0.4)" font-size="9">0%</text>
                                            </svg>
                                        {:else}
                                            <div class="emptyState xsmall">No drawdown data</div>
                                        {/if}
                                    </div>
                                </div>
                            {/each}
                        </div>

                        <div class="sectionTitle">Detailed Drawdown Episodes</div>
                        {#each ddRows as dd}
                            {#if dd.episodes && dd.episodes.length > 0}
                                <div class="episodeBlock">
                                    <div class="episodeHeader">
                                        <span class="mono bold">{dd.ticker}</span>
                                        <span class="soft">{dd.metrics.num_drawdown_episodes} episodes found</span>
                                    </div>
                                    <div class="tableWrap">
                                        <table class="kittTable xsmallTable">
                                            <thead>
                                            <tr>
                                                <th>Start</th>
                                                <th>Trough</th>
                                                <th>End</th>
                                                <th>Duration</th>
                                                <th>Depth</th>
                                            </tr>
                                            </thead>
                                            <tbody>
                                            {#each [...dd.episodes].sort((a,b) => a.max_drawdown - b.max_drawdown).slice(0, 5) as ep}
                                                <tr>
                                                    <td><span class="mono">{ep.start_date}</span></td>
                                                    <td><span class="mono">{ep.trough_date}</span></td>
                                                    <td><span class="mono">{ep.end_date ?? "Ongoing"}</span></td>
                                                    <td><span class="mono">{ep.duration_days}d</span></td>
                                                    <td><span class="mono redText">{formatPct(ep.max_drawdown)}</span></td>
                                                </tr>
                                            {/each}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            {/if}
                        {/each}
                    {/if}
                </div>
            {/if}

            <!-- TRANSACTIONS LOG -->
            {#if view === "log"}
                <div class="modulePanel">
                    <div class="moduleHead">
                        <div class="panelLabel">TRANSACTIONS LOG</div>
                        <div class="moduleHint">{transactions.length} transaction(s)</div>
                    </div>

                    {#if transactions.length > 0}
                        <div class="tableWrap">
                            <table class="kittTable">
                                <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Symbol</th>
                                    <th>Side</th>
                                    <th>Quantity</th>
                                    <th>Price</th>
                                    <th>Fee</th>
                                    <th>Amount</th>
                                    <th>Ccy</th>
                                    <th></th>
                                </tr>
                                </thead>
                                <tbody>
                                {#each transactions as tx (tx.id)}
                                    <tr>
                                        <td><span class="mono">{tx.date}</span></td>
                                        <td><span class="mono">{tx.symbol}</span></td>
                                        <td>
                                            <span class="sidePill" class:buy={tx.side === "BUY"} class:sell={tx.side === "SELL"}>
                                                {tx.side}
                                            </span>
                                        </td>
                                        <td><span class="mono">{formatNum(tx.quantity, 4)}</span></td>
                                        <td><span class="mono">{formatNum(tx.price, 4)}</span></td>
                                        <td><span class="mono">{formatNum(tx.transaction_fee, 2)}</span></td>
                                        <td><span class="mono">{formatNum(tx.amount, 2)}</span></td>
                                        <td><span class="mono">{tx.currency ?? "—"}</span></td>
                                        <td>
                                            <button class="btn xsmall ghost" type="button"
                                                    on:click={() => deleteTransaction(tx.id)}
                                                    disabled={isDeletingId === tx.id}>
                                                {isDeletingId === tx.id ? "…" : "Delete"}
                                            </button>
                                        </td>
                                    </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {:else if isLoadingData}
                        <div class="emptyState">Loading transactions…</div>
                    {:else}
                        <div class="emptyState">No transactions logged yet. Use the form above to create one.</div>
                    {/if}
                </div>
            {/if}
        </div>
    </section>
</div>

<style>
    .page {
        min-height: 100vh;
        padding: 16px;
        display: flex;
        justify-content: center;
        align-items: center;
        background:
                radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
                linear-gradient(180deg, #07080c, #04040a);
        color: rgba(255, 255, 255, 0.9);
        box-sizing: border-box;
    }

    .card {
        width: min(1500px, 100%);
        max-height: calc(100vh - 32px);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow:
                0 0 0 1px rgba(255, 0, 60, 0.08),
                0 20px 60px rgba(0, 0, 0, 0.65),
                0 0 30px rgba(255, 0, 60, 0.08);
        overflow: hidden;
        position: relative;
        display: flex;
        flex-direction: column;
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
        0% {
            transform: translateY(-120px);
        }

        100% {
            transform: translateY(320px);
        }
    }

    .header {
        padding: 14px 16px 12px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background:
                linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
                linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
        flex-shrink: 0;
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
    }

    .status,
    .chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.10);
        padding: 5px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .status.soft {
        background: rgba(255, 0, 60, 0.06);
        color: rgba(255, 255, 255, 0.74);
    }

    .chipRow {
        margin-top: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }

    .chip {
        color: rgba(235, 235, 245, 0.72);
        background: rgba(255, 0, 60, 0.07);
    }

    .body {
        padding: 12px;
        display: grid;
        gap: 12px;
        overflow: auto;
        min-height: 0;
    }

    .topBar {
        display: flex;
        gap: 10px;
        align-items: flex-end;
        flex-wrap: wrap;
    }

    .topBar .field {
        min-width: 240px;
        flex: 1 1 240px;
    }

    .viewSwitch {
        display: inline-flex;
        gap: 0;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        overflow: hidden;
        background: rgba(0, 0, 0, 0.22);
    }

    .switchBtn {
        appearance: none;
        background: transparent;
        border: none;
        color: rgba(235, 235, 245, 0.72);
        padding: 8px 12px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
        transition: background 140ms ease, color 140ms ease;
    }

    .switchBtn:hover {
        color: rgba(255, 255, 255, 0.95);
        background: rgba(255, 0, 60, 0.06);
    }

    .switchBtn.active {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.35), rgba(255, 0, 60, 0.18));
        color: rgba(255, 255, 255, 0.98);
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.22);
    }

    .formCard {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 10px 12px;
    }

    .formCard summary {
        list-style: none;
        cursor: pointer;
        padding: 4px 0;
        display: flex;
        align-items: center;
    }

    .formCard summary::-webkit-details-marker {
        display: none;
    }

    .formCard summary::before {
        content: "▸";
        margin-right: 10px;
        transition: transform 140ms ease;
        color: rgba(255, 0, 60, 0.85);
    }

    .formCard[open] summary::before {
        transform: rotate(90deg);
    }

    .panelLabel {
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
    }

    .moduleHint {
        font-size: 11px;
        color: rgba(235, 235, 245, 0.48);
        font-family: ui-monospace, monospace;
    }

    .modulePanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 12px;
        min-width: 0;
    }

    .moduleHead {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 10px;
        margin-bottom: 10px;
        flex-wrap: wrap;
    }

    .formGrid {
        margin-top: 10px;
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
    }

    @media (max-width: 1100px) {
        .formGrid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 600px) {
        .formGrid {
            grid-template-columns: 1fr;
        }
    }

    .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
        min-width: 0;
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
        padding: 8px 10px;
        outline: none;
        width: 100%;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10);
        box-sizing: border-box;
    }

    .input:focus {
        border-color: rgba(255, 0, 60, 0.55);
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
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
        padding: 8px 12px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 255, 255, 0.90);
        font-size: 12px;
        cursor: pointer;
        transition: transform 140ms ease, border 140ms ease;
    }

    .btn:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
    }

    .btn:disabled {
        opacity: 0.55;
        cursor: not-allowed;
        transform: none;
    }

    .btn.ghost {
        background: rgba(255, 255, 255, 0.02);
        border-color: rgba(255, 255, 255, 0.10);
        color: rgba(235, 235, 245, 0.75);
    }

    .btn.ghost:hover {
        border-color: rgba(255, 255, 255, 0.25);
    }

    .btn.primary {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.40), rgba(255, 0, 60, 0.22));
        border-color: rgba(255, 0, 60, 0.65);
        color: rgba(255, 255, 255, 0.98);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.26), 0 0 22px rgba(255, 0, 60, 0.30);
        font-weight: 600;
    }

    .btn.xsmall {
        padding: 6px 10px;
        font-size: 11px;
    }

    .errorBox,
    .okBox {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 12px;
        font-size: 13px;
        line-height: 1.4;
    }

    .errorBox {
        border: 1px solid rgba(255, 0, 60, 0.30);
        background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 230, 235, 0.95);
    }

    .okBox {
        border: 1px solid rgba(34, 197, 94, 0.30);
        background: rgba(34, 197, 94, 0.10);
        color: rgba(200, 255, 220, 0.95);
    }

    .kpiRow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 8px;
        margin-bottom: 10px;
    }

    .grid2 {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
        margin-top: 16px;
    }

    @media (max-width: 1100px) {
        .grid2 {
            grid-template-columns: 1fr;
        }
    }

    .sectionTitle {
        font-size: 13px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.7);
        margin-bottom: 8px;
        margin-top: 16px;
        padding-left: 4px;
        border-left: 2px solid rgba(255, 0, 60, 0.5);
    }

    .analyticsSettings {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 16px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .inlineField {
        flex-direction: row !important;
        align-items: center;
        gap: 16px !important;
    }

    .inputGroup {
        display: flex;
        gap: 8px;
        align-items: center;
    }

    .xsmallInput {
        width: 120px !important;
        padding: 4px 8px !important;
        font-size: 12px !important;
    }

    .episodeBlock {
        margin-bottom: 24px;
        background: rgba(255, 255, 255, 0.01);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 16px;
    }

    .episodeHeader {
        display: flex;
        justify-content: space-between;
        margin-bottom: 12px;
        align-items: center;
    }

    .xsmallTable {
        font-size: 12px;
    }

    .xsmallTable th, .xsmallTable td {
        padding: 6px 8px;
    }

    .chartGrid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
        gap: 16px;
        margin-top: 16px;
    }

    .chartCard {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .chartHeader {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        padding-bottom: 8px;
    }

    .chartWrap {
        height: 100px;
        position: relative;
    }

    .miniChart {
        width: 100%;
        height: 100%;
        overflow: visible;
    }

    .bold {
        font-weight: 600;
        color: #fff;
    }

    .xsmall {
        font-size: 11px;
    }

    @media (max-width: 1100px) {
        .kpiRow {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 600px) {
        .kpiRow {
            grid-template-columns: 1fr;
        }
    }

    .kpiCard {
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: rgba(255, 0, 60, 0.04);
        border-radius: 12px;
        padding: 8px 10px;
        min-width: 0;
    }

    .kpiK {
        font-size: 10px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.55);
        margin-bottom: 4px;
    }

    .kpiV {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.92);
    }

    .tableWrap {
        overflow: auto;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
        max-height: 48vh;
        max-width: 100%;
    }

    .kittTable {
        width: 100%;
        min-width: 980px;
        border-collapse: separate;
        border-spacing: 0;
        background: rgba(0, 0, 0, 0.25);
        table-layout: auto;
    }

    .kittTable thead th {
        text-align: left;
        font-size: 10px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
        padding: 8px 10px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky;
        top: 0;
        z-index: 1;
        white-space: nowrap;
    }

    .kittTable tbody td {
        padding: 7px 10px;
        font-size: 12px;
        color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.08);
        white-space: nowrap;
    }

    .nameCell {
        max-width: 160px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .greenText {
        color: rgba(34, 197, 94, 0.96);
    }

    .redText {
        color: rgba(255, 80, 100, 0.96);
    }

    .soft {
        color: rgba(235, 235, 245, 0.55);
    }

    .sidePill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 11px;
        letter-spacing: 0.08em;
        font-family: ui-monospace, monospace;
    }

    .sidePill.buy {
        background: rgba(34, 197, 94, 0.16);
        color: rgba(180, 255, 200, 0.95);
        border: 1px solid rgba(34, 197, 94, 0.30);
    }

    .sidePill.sell {
        background: rgba(255, 0, 60, 0.16);
        color: rgba(255, 210, 220, 0.95);
        border: 1px solid rgba(255, 0, 60, 0.35);
    }

    .emptyState {
        color: rgba(235, 235, 245, 0.55);
        padding: 12px 4px;
        font-size: 13px;
    }

    @media (max-width: 800px) {
        .page {
            padding: 8px;
        }

        .card {
            max-height: calc(100vh - 16px);
            border-radius: 12px;
        }

        .header {
            padding: 12px;
        }

        .body {
            padding: 10px;
            gap: 10px;
        }

        .topBar,
        .viewSwitch,
        .btn.ghost {
            width: 100%;
        }

        .viewSwitch {
            display: grid;
            grid-template-columns: 1fr 1fr;
        }

        .switchBtn,
        .btn {
            width: 100%;
        }

        .tableWrap {
            max-height: 42vh;
        }

        .kittTable {
            min-width: 860px;
        }
    }
</style>
