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

    type MonteCarloResult = {
        dates: string[];
        percentiles: { p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };
        samples: number[][];
        stats: {
            n_simulations: number;
            horizon_days: number;
            lookback_start: string;
            lookback_end: string;
            initial_value: number;
            expected_final: number;
            p5_final: number;
            p25_final: number;
            p50_final: number;
            p75_final: number;
            p95_final: number;
            annualized_drift: number;
            annualized_volatility: number;
            prob_positive: number;
        };
        tickers: string[];
        weights: number[];
        errors: Record<string, string>;
    };

    let mcResult: MonteCarloResult | null = null;
    let mcHorizonDays = 252;
    let mcNSimulations = 1000;
    let mcLookback = "3Y";
    let isFetchingMC = false;
    let mcError = "";

    type CorrelationPair = {
        ticker_a: string;
        ticker_b: string;
        correlation: number;
    };

    type CorrelationStats = {
        avg_correlation: number;
        weighted_avg_correlation: number | null;
        min_pair: CorrelationPair | null;
        max_pair: CorrelationPair | null;
        pct_pairs_above_0_7: number;
        pct_pairs_below_0_3: number;
        diversification_score: number;
        n_pairs: number;
    };

    type CorrelationResult = {
        tickers: string[];
        matrix: number[][];
        observations: number;
        start_date_used: string;
        end_date_used: string;
        stats: CorrelationStats;
        errors: Record<string, string>;
    };

    let corrResult: CorrelationResult | null = null;
    let corrLookback = "3Y";
    let isFetchingCorr = false;
    let corrError = "";

    type PortfolioHealthStats = {
        annualized_return: number;
        annualized_volatility: number;
        sharpe_ratio: number;
        sortino_ratio: number;
        calmar_ratio: number;
        max_drawdown: number;
        best_day: number;
        worst_day: number;
        pct_positive_days: number;
        cumulative_return: number;
    };

    type PortfolioHealthResult = {
        tickers: string[];
        weights: number[];
        observations: number;
        start_date_used: string;
        end_date_used: string;
        risk_free_rate: number;
        stats: PortfolioHealthStats;
        errors: Record<string, string>;
    };

    let healthResult: PortfolioHealthResult | null = null;
    let healthLookback = "3Y";
    let healthRf = 0.02;
    let isFetchingHealth = false;
    let healthError = "";

    type FrontierPoint = {
        expected_return: number;
        volatility: number;
        sharpe: number;
    };

    type PortfolioOnFrontier = {
        weights: Record<string, number>;
        expected_return: number;
        volatility: number;
        sharpe: number;
    };

    type AssetPoint = {
        ticker: string;
        expected_return: number;
        volatility: number;
    };

    type EfficientFrontierResult = {
        tickers: string[];
        risk_free_rate: number;
        observations: number;
        start_date_used: string;
        end_date_used: string;
        frontier: FrontierPoint[];
        assets: AssetPoint[];
        min_variance: PortfolioOnFrontier;
        max_sharpe: PortfolioOnFrontier;
        current_portfolio: PortfolioOnFrontier | null;
        errors: Record<string, string>;
    };

    let efResult: EfficientFrontierResult | null = null;
    let efLookback = "3Y";
    let efRf = 0.02;
    let isFetchingEF = false;
    let efError = "";

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

    async function runMonteCarlo() {
        if (!positionView || positionView.rows.length === 0) {
            mcError = "No positions to simulate.";
            return;
        }
        const eligible = positionView.rows.filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length === 0) {
            mcError = "No positions with a valid market weight.";
            return;
        }
        isFetchingMC = true;
        mcError = "";
        try {
            const payload = {
                tickers: eligible.map(r => r.symbol),
                weights: eligible.map(r => r.weight as number),
                horizon_days: mcHorizonDays,
                n_simulations: mcNSimulations,
                lookback_period: mcLookback,
                auto_adjust: true,
                initial_value: positionView.total_market_value || 1.0,
                n_sample_paths: 30,
                seed: 42
            };
            const res = await instance.post<MonteCarloResult>("/analytics/yahoo/monte-carlo", payload);
            mcResult = res.data;
        } catch (err: any) {
            mcError = err?.response?.data?.detail || err?.message || "Unable to run Monte Carlo simulation.";
            mcResult = null;
        } finally {
            isFetchingMC = false;
        }
    }

    async function runEfficientFrontier() {
        if (!positionView || positionView.rows.length < 2) {
            efError = "Need at least 2 positions to compute the frontier.";
            efResult = null;
            return;
        }
        const eligible = positionView.rows.filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length < 2) {
            efError = "Need at least 2 positions with a valid market weight.";
            efResult = null;
            return;
        }
        isFetchingEF = true;
        efError = "";
        try {
            const payload = {
                tickers: eligible.map(r => r.symbol),
                weights: eligible.map(r => r.weight as number),
                lookback_period: efLookback,
                auto_adjust: true,
                risk_free_rate: efRf,
                n_points: 50
            };
            const res = await instance.post<EfficientFrontierResult>("/analytics/yahoo/efficient-frontier", payload);
            efResult = res.data;
        } catch (err: any) {
            efError = err?.response?.data?.detail || err?.message || "Unable to compute efficient frontier.";
            efResult = null;
        } finally {
            isFetchingEF = false;
        }
    }

    // Efficient frontier chart geometry
    const EF_W = 960;
    const EF_H = 420;
    const EF_PAD = { top: 24, right: 24, bottom: 44, left: 64 };

    function getEFChartData(r: EfficientFrontierResult | null) {
        if (!r) return null;
        const allX: number[] = [];
        const allY: number[] = [];
        r.frontier.forEach(p => { allX.push(p.volatility); allY.push(p.expected_return); });
        r.assets.forEach(a => { allX.push(a.volatility); allY.push(a.expected_return); });
        allX.push(r.min_variance.volatility, r.max_sharpe.volatility);
        allY.push(r.min_variance.expected_return, r.max_sharpe.expected_return);
        if (r.current_portfolio) {
            allX.push(r.current_portfolio.volatility);
            allY.push(r.current_portfolio.expected_return);
        }
        // Include (0, Rf) for the CML origin
        allX.push(0);
        allY.push(r.risk_free_rate);

        const xMin = 0;
        const xMax = Math.max(...allX) * 1.05;
        const yLo = Math.min(...allY);
        const yHi = Math.max(...allY);
        const yPad = (yHi - yLo) * 0.10 || 0.01;
        const yMin = yLo - yPad;
        const yMax = yHi + yPad;

        const innerW = EF_W - EF_PAD.left - EF_PAD.right;
        const innerH = EF_H - EF_PAD.top - EF_PAD.bottom;

        const xAt = (v: number) => EF_PAD.left + ((v - xMin) / (xMax - xMin || 1)) * innerW;
        const yAt = (v: number) => EF_PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;

        const frontierPath = r.frontier.length > 1
            ? "M " + r.frontier.map(p => `${xAt(p.volatility)} ${yAt(p.expected_return)}`).join(" L ")
            : "";

        // CML: line from (0, Rf) with slope = max_sharpe; extend to chart's right edge
        const slope = r.max_sharpe.sharpe;
        const cmlX2 = xMax;
        const cmlY2 = r.risk_free_rate + slope * cmlX2;
        const cml = { x1: xAt(0), y1: yAt(r.risk_free_rate), x2: xAt(cmlX2), y2: yAt(cmlY2) };

        // Y/X ticks (5)
        const xTicks: { value: number; x: number }[] = [];
        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 5; i++) {
            const vx = xMin + ((xMax - xMin) * i) / 5;
            xTicks.push({ value: vx, x: xAt(vx) });
            const vy = yMin + ((yMax - yMin) * i) / 5;
            yTicks.push({ value: vy, y: yAt(vy) });
        }

        return {
            xAt, yAt,
            frontierPath,
            cml,
            xTicks, yTicks,
            xMin, xMax, yMin, yMax,
        };
    }

    async function runPortfolioHealth() {
        if (!positionView || positionView.rows.length === 0) {
            healthError = "No positions to analyze.";
            healthResult = null;
            return;
        }
        const eligible = positionView.rows.filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length === 0) {
            healthError = "No positions with a valid market weight.";
            healthResult = null;
            return;
        }
        isFetchingHealth = true;
        healthError = "";
        try {
            const payload = {
                tickers: eligible.map(r => r.symbol),
                weights: eligible.map(r => r.weight as number),
                lookback_period: healthLookback,
                auto_adjust: true,
                risk_free_rate: healthRf
            };
            const res = await instance.post<PortfolioHealthResult>("/analytics/yahoo/portfolio-health", payload);
            healthResult = res.data;
        } catch (err: any) {
            healthError = err?.response?.data?.detail || err?.message || "Unable to compute portfolio health.";
            healthResult = null;
        } finally {
            isFetchingHealth = false;
        }
    }

    function sharpeClass(v: number): string {
        if (v >= 1) return "greenText";
        if (v < 0) return "redText";
        return "";
    }

    function sharpeVerdict(v: number): string {
        if (v >= 2) return "Excellent";
        if (v >= 1) return "Good";
        if (v >= 0.5) return "Acceptable";
        if (v >= 0) return "Poor";
        return "Negative";
    }

    async function runCorrelation() {
        if (!positionView || positionView.rows.length < 2) {
            corrError = "Need at least 2 positions to compute correlations.";
            corrResult = null;
            return;
        }
        isFetchingCorr = true;
        corrError = "";
        try {
            const tickers = positionView.rows.map(r => r.symbol);
            const weights = positionView.rows.map(r => r.weight ?? 0);
            const hasWeights = weights.some(w => w > 0);
            const payload: Record<string, any> = {
                tickers,
                lookback_period: corrLookback,
                auto_adjust: true,
                return_mode: "log"
            };
            if (hasWeights) payload.weights = weights;
            const res = await instance.post<CorrelationResult>("/analytics/yahoo/correlation", payload);
            corrResult = res.data;
        } catch (err: any) {
            corrError = err?.response?.data?.detail || err?.message || "Unable to compute correlations.";
            corrResult = null;
        } finally {
            isFetchingCorr = false;
        }
    }

    function corrCellColor(v: number): string {
        // Blue (-1) -> white (0) -> red (+1)
        const c = Math.max(-1, Math.min(1, v));
        if (c >= 0) {
            // white -> red
            const r = 255;
            const g = Math.round(255 * (1 - c));
            const b = Math.round(255 * (1 - c));
            return `rgba(${r}, ${g}, ${b}, ${0.18 + 0.55 * c})`;
        } else {
            // white -> blue
            const r = Math.round(255 * (1 + c));
            const g = Math.round(255 * (1 + c));
            const b = 255;
            return `rgba(${r}, ${g}, ${b}, ${0.18 + 0.55 * (-c)})`;
        }
    }

    function corrTextColor(v: number): string {
        const a = Math.abs(v);
        return a > 0.5 ? "#0a0a12" : "rgba(255,255,255,0.85)";
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

    // Monte Carlo chart dimensions (full-width, taller)
    const MC_W = 960;
    const MC_H = 380;
    const MC_PAD = { top: 20, right: 60, bottom: 28, left: 70 };

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

    function getMonteCarloChartData(result: MonteCarloResult | null) {
        if (!result) return null;
        const { percentiles, samples, stats } = result;
        const n = percentiles.p5.length;
        if (n < 2) return null;

        const allValues: number[] = [
            ...percentiles.p5,
            ...percentiles.p95,
            ...samples.flat(),
            stats.initial_value
        ];
        const minVal = Math.min(...allValues);
        const maxVal = Math.max(...allValues);
        const pad = (maxVal - minVal) * 0.05 || 0.01;
        const yMin = minVal - pad;
        const yMax = maxVal + pad;
        const range = yMax - yMin;

        const innerW = MC_W - MC_PAD.left - MC_PAD.right;
        const innerH = MC_H - MC_PAD.top - MC_PAD.bottom;

        const xAt = (i: number) => MC_PAD.left + (i / (n - 1)) * innerW;
        const yAt = (v: number) => MC_PAD.top + (1 - (v - yMin) / range) * innerH;

        const toPath = (arr: number[]) =>
            buildLinePath(arr.map((v, i) => ({ x: xAt(i), y: yAt(v) })));

        const bandPath = (lower: number[], upper: number[]) => {
            const top = upper.map((v, i) => `${xAt(i)} ${yAt(v)}`);
            const bot = lower.map((v, i) => `${xAt(i)} ${yAt(v)}`).reverse();
            return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
        };

        const initialY = yAt(stats.initial_value);
        const baselineY = Number.isFinite(initialY) ? initialY : MC_H - MC_PAD.bottom;

        const yTicks = 5;
        const tickValues: { value: number; y: number }[] = [];
        for (let i = 0; i <= yTicks; i++) {
            const v = yMin + (range * i) / yTicks;
            tickValues.push({ value: v, y: yAt(v) });
        }

        const xTickCount = Math.min(6, n);
        const xTicks: { date: string; x: number }[] = [];
        for (let i = 0; i < xTickCount; i++) {
            const idx = Math.round((i / (xTickCount - 1)) * (n - 1));
            xTicks.push({ date: result.dates[idx] ?? "", x: xAt(idx) });
        }

        return {
            bandOuter: bandPath(percentiles.p5, percentiles.p95),
            bandInner: bandPath(percentiles.p25, percentiles.p75),
            median: toPath(percentiles.p50),
            samplePaths: samples.map(s => toPath(s)),
            baselineY,
            yTicks: tickValues,
            xTicks,
            yMin,
            yMax,
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

                    <!-- PORTFOLIO HEALTH -->
                    <div class="mcSection">
                        <div class="sectionTitle">Portfolio Health · Sharpe & Risk-Adjusted Ratios</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={healthLookback}>
                                    <option value="6M">6 Months</option>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Risk-free rate</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001" bind:value={healthRf} />
                            </label>
                            <button class="btn primary xsmall" on:click={runPortfolioHealth}
                                    disabled={isFetchingHealth || !positionView || positionView.rows.length === 0}>
                                {isFetchingHealth ? "Computing…" : "Compute health"}
                            </button>
                        </div>

                        {#if healthError}
                            <div class="errorBox">{healthError}</div>
                        {/if}

                        {#if healthResult}
                            <div class="healthHeadline">
                                <div class="healthBigKpi">
                                    <div class="healthBigLabel">Sharpe ratio</div>
                                    <div class="healthBigValue mono {sharpeClass(healthResult.stats.sharpe_ratio)}">
                                        {healthResult.stats.sharpe_ratio.toFixed(2)}
                                    </div>
                                    <div class="healthVerdict mono soft">{sharpeVerdict(healthResult.stats.sharpe_ratio)}</div>
                                </div>
                                <div class="healthSubGrid">
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Sortino ratio</div>
                                        <div class="mcStatValue mono {sharpeClass(healthResult.stats.sortino_ratio)}">{healthResult.stats.sortino_ratio.toFixed(2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Calmar ratio</div>
                                        <div class="mcStatValue mono {sharpeClass(healthResult.stats.calmar_ratio)}">{healthResult.stats.calmar_ratio.toFixed(2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Ann. return</div>
                                        <div class="mcStatValue mono {pnlClass(healthResult.stats.annualized_return)}">{formatPct(healthResult.stats.annualized_return)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Ann. volatility</div>
                                        <div class="mcStatValue mono">{formatPct(healthResult.stats.annualized_volatility)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Max drawdown</div>
                                        <div class="mcStatValue mono redText">{formatPct(healthResult.stats.max_drawdown)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Cumulative return</div>
                                        <div class="mcStatValue mono {pnlClass(healthResult.stats.cumulative_return)}">{formatPct(healthResult.stats.cumulative_return)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Best day</div>
                                        <div class="mcStatValue mono greenText">{formatPct(healthResult.stats.best_day)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Worst day</div>
                                        <div class="mcStatValue mono redText">{formatPct(healthResult.stats.worst_day)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">% positive days</div>
                                        <div class="mcStatValue mono">{formatPct(healthResult.stats.pct_positive_days)}</div>
                                    </div>
                                </div>
                            </div>

                            <div class="mcFootnote soft">
                                {healthResult.observations} daily observations · {healthResult.start_date_used} → {healthResult.end_date_used} · Rf = {formatPct(healthResult.risk_free_rate)} annualized · fixed-weight rebalanced daily
                                {#if Object.keys(healthResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(healthResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingHealth}
                            <div class="emptyState">Click "Compute health" to assess your portfolio's risk-adjusted performance over the last {healthLookback}.</div>
                        {/if}
                    </div>

                    <!-- EFFICIENT FRONTIER (Markowitz) -->
                    <div class="mcSection">
                        <div class="sectionTitle">Markowitz · Efficient Frontier</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={efLookback}>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Risk-free rate</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001" bind:value={efRf} />
                            </label>
                            <button class="btn primary xsmall" on:click={runEfficientFrontier}
                                    disabled={isFetchingEF || !positionView || positionView.rows.length < 2}>
                                {isFetchingEF ? "Optimizing…" : "Compute frontier"}
                            </button>
                        </div>

                        {#if efError}
                            <div class="errorBox">{efError}</div>
                        {/if}

                        {#if efResult}
                            {@const ef = getEFChartData(efResult)}
                            {#if ef}
                                <div class="efChartWrap">
                                    <svg viewBox="0 0 {EF_W} {EF_H}" class="mcChart" preserveAspectRatio="xMidYMid meet">
                                        <!-- Y gridlines + labels -->
                                        {#each ef.yTicks as tick}
                                            <line x1={EF_PAD.left} y1={tick.y} x2={EF_W - EF_PAD.right} y2={tick.y} stroke="rgba(255,255,255,0.06)" stroke-width="1" />
                                            <text x={EF_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)" font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <!-- X gridlines + labels -->
                                        {#each ef.xTicks as tick}
                                            <line x1={tick.x} y1={EF_PAD.top} x2={tick.x} y2={EF_H - EF_PAD.bottom} stroke="rgba(255,255,255,0.04)" stroke-width="1" />
                                            <text x={tick.x} y={EF_H - EF_PAD.bottom + 16} fill="rgba(255,255,255,0.45)" font-size="10" text-anchor="middle" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <!-- Axis labels -->
                                        <text x={EF_W / 2} y={EF_H - 6} fill="rgba(255,255,255,0.55)" font-size="11" text-anchor="middle">Annualized volatility</text>
                                        <text x={14} y={EF_H / 2} fill="rgba(255,255,255,0.55)" font-size="11" text-anchor="middle" transform="rotate(-90 14 {EF_H / 2})">Annualized return</text>

                                        <!-- Capital Market Line -->
                                        <line x1={ef.cml.x1} y1={ef.cml.y1} x2={ef.cml.x2} y2={ef.cml.y2}
                                              stroke="rgba(255, 215, 0, 0.55)" stroke-width="1.2" stroke-dasharray="5 4" />

                                        <!-- Efficient frontier curve -->
                                        {#if ef.frontierPath}
                                            <path d={ef.frontierPath} fill="none" stroke="rgba(0, 212, 255, 0.95)" stroke-width="2.2" />
                                        {/if}

                                        <!-- Individual asset points -->
                                        {#each efResult.assets as a}
                                            <g>
                                                <circle cx={ef.xAt(a.volatility)} cy={ef.yAt(a.expected_return)} r="4"
                                                        fill="rgba(235, 235, 245, 0.6)" stroke="rgba(0,0,0,0.4)" stroke-width="0.6">
                                                    <title>{a.ticker}: vol {(a.volatility*100).toFixed(1)}%, ret {(a.expected_return*100).toFixed(1)}%</title>
                                                </circle>
                                                <text x={ef.xAt(a.volatility) + 7} y={ef.yAt(a.expected_return) + 3}
                                                      fill="rgba(235, 235, 245, 0.65)" font-size="10" class="mono">{a.ticker}</text>
                                            </g>
                                        {/each}

                                        <!-- Min variance point -->
                                        <circle cx={ef.xAt(efResult.min_variance.volatility)} cy={ef.yAt(efResult.min_variance.expected_return)} r="7"
                                                fill="rgba(34, 197, 94, 0.95)" stroke="#fff" stroke-width="1.2">
                                            <title>Min variance · vol {(efResult.min_variance.volatility*100).toFixed(2)}%, ret {(efResult.min_variance.expected_return*100).toFixed(2)}%, Sharpe {efResult.min_variance.sharpe.toFixed(2)}</title>
                                        </circle>

                                        <!-- Max Sharpe (tangent) point -->
                                        <circle cx={ef.xAt(efResult.max_sharpe.volatility)} cy={ef.yAt(efResult.max_sharpe.expected_return)} r="7"
                                                fill="rgba(255, 215, 0, 0.95)" stroke="#fff" stroke-width="1.2">
                                            <title>Tangent / Max Sharpe · vol {(efResult.max_sharpe.volatility*100).toFixed(2)}%, ret {(efResult.max_sharpe.expected_return*100).toFixed(2)}%, Sharpe {efResult.max_sharpe.sharpe.toFixed(2)}</title>
                                        </circle>

                                        <!-- Current portfolio point -->
                                        {#if efResult.current_portfolio}
                                            <circle cx={ef.xAt(efResult.current_portfolio.volatility)} cy={ef.yAt(efResult.current_portfolio.expected_return)} r="8"
                                                    fill="rgba(255, 0, 60, 0.95)" stroke="#fff" stroke-width="1.5">
                                                <title>Your portfolio · vol {(efResult.current_portfolio.volatility*100).toFixed(2)}%, ret {(efResult.current_portfolio.expected_return*100).toFixed(2)}%, Sharpe {efResult.current_portfolio.sharpe.toFixed(2)}</title>
                                            </circle>
                                        {/if}

                                        <!-- Legend -->
                                        <g transform="translate({EF_W - EF_PAD.right - 200}, {EF_PAD.top + 6})">
                                            <line x1="0" y1="6" x2="18" y2="6" stroke="rgba(0, 212, 255, 0.95)" stroke-width="2.2" />
                                            <text x="24" y="10" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Efficient frontier</text>
                                            <line x1="0" y1="22" x2="18" y2="22" stroke="rgba(255, 215, 0, 0.55)" stroke-width="1.2" stroke-dasharray="5 4" />
                                            <text x="24" y="26" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Capital Market Line</text>
                                            <circle cx="9" cy="38" r="5" fill="rgba(255, 215, 0, 0.95)" stroke="#fff" stroke-width="1" />
                                            <text x="24" y="42" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Tangent (max Sharpe)</text>
                                            <circle cx="9" cy="54" r="5" fill="rgba(34, 197, 94, 0.95)" stroke="#fff" stroke-width="1" />
                                            <text x="24" y="58" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Min variance</text>
                                            {#if efResult.current_portfolio}
                                                <circle cx="9" cy="70" r="6" fill="rgba(255, 0, 60, 0.95)" stroke="#fff" stroke-width="1.2" />
                                                <text x="24" y="74" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Your portfolio</text>
                                            {/if}
                                            <circle cx="9" cy="86" r="4" fill="rgba(235, 235, 245, 0.6)" stroke="rgba(0,0,0,0.4)" stroke-width="0.6" />
                                            <text x="24" y="90" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">Individual asset</text>
                                        </g>
                                    </svg>
                                </div>

                                <div class="efSummary">
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Max Sharpe (tangent)</div>
                                        <div class="mcStatValue mono greenText">{efResult.max_sharpe.sharpe.toFixed(2)}</div>
                                        <div class="mono soft xsmall">vol {formatPct(efResult.max_sharpe.volatility)} · ret {formatPct(efResult.max_sharpe.expected_return)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Min variance</div>
                                        <div class="mcStatValue mono">{efResult.min_variance.sharpe.toFixed(2)}</div>
                                        <div class="mono soft xsmall">vol {formatPct(efResult.min_variance.volatility)} · ret {formatPct(efResult.min_variance.expected_return)}</div>
                                    </div>
                                    {#if efResult.current_portfolio}
                                        {@const cur = efResult.current_portfolio}
                                        {@const gap = efResult.max_sharpe.sharpe - cur.sharpe}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Your portfolio</div>
                                            <div class="mcStatValue mono {sharpeClass(cur.sharpe)}">{cur.sharpe.toFixed(2)}</div>
                                            <div class="mono soft xsmall">vol {formatPct(cur.volatility)} · ret {formatPct(cur.expected_return)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Sharpe gap vs tangent</div>
                                            <div class="mcStatValue mono {gap > 0.3 ? 'redText' : ''}">−{gap.toFixed(2)}</div>
                                            <div class="mono soft xsmall">{gap > 0.3 ? "Significant room to improve" : gap > 0.1 ? "Near-optimal" : "On the frontier"}</div>
                                        </div>
                                    {/if}
                                </div>

                                <div class="efWeightsGrid">
                                    <div>
                                        <div class="efWeightsTitle">Tangent (max Sharpe) weights</div>
                                        <div class="tableWrap">
                                            <table class="kittTable xsmallTable">
                                                <thead>
                                                <tr>
                                                    <th>Ticker</th>
                                                    <th>Suggested</th>
                                                    {#if efResult.current_portfolio}
                                                        <th>Current</th>
                                                        <th>Δ</th>
                                                    {/if}
                                                </tr>
                                                </thead>
                                                <tbody>
                                                {#each efResult.tickers as t}
                                                    {@const sugg = efResult.max_sharpe.weights[t] ?? 0}
                                                    {@const cur = efResult.current_portfolio?.weights[t] ?? 0}
                                                    {@const delta = sugg - cur}
                                                    <tr>
                                                        <td><span class="mono">{t}</span></td>
                                                        <td><span class="mono">{formatPct(sugg)}</span></td>
                                                        {#if efResult.current_portfolio}
                                                            <td><span class="mono soft">{formatPct(cur)}</span></td>
                                                            <td><span class="mono {delta > 0 ? 'greenText' : delta < 0 ? 'redText' : ''}">{delta > 0 ? "+" : ""}{formatPct(delta)}</span></td>
                                                        {/if}
                                                    </tr>
                                                {/each}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div>
                                        <div class="efWeightsTitle">Min variance weights</div>
                                        <div class="tableWrap">
                                            <table class="kittTable xsmallTable">
                                                <thead>
                                                <tr>
                                                    <th>Ticker</th>
                                                    <th>Suggested</th>
                                                    {#if efResult.current_portfolio}
                                                        <th>Current</th>
                                                        <th>Δ</th>
                                                    {/if}
                                                </tr>
                                                </thead>
                                                <tbody>
                                                {#each efResult.tickers as t}
                                                    {@const sugg = efResult.min_variance.weights[t] ?? 0}
                                                    {@const cur = efResult.current_portfolio?.weights[t] ?? 0}
                                                    {@const delta = sugg - cur}
                                                    <tr>
                                                        <td><span class="mono">{t}</span></td>
                                                        <td><span class="mono">{formatPct(sugg)}</span></td>
                                                        {#if efResult.current_portfolio}
                                                            <td><span class="mono soft">{formatPct(cur)}</span></td>
                                                            <td><span class="mono {delta > 0 ? 'greenText' : delta < 0 ? 'redText' : ''}">{delta > 0 ? "+" : ""}{formatPct(delta)}</span></td>
                                                        {/if}
                                                    </tr>
                                                {/each}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                            {/if}

                            <div class="mcFootnote soft">
                                {efResult.observations} daily log-return observations · {efResult.start_date_used} → {efResult.end_date_used} · Rf = {formatPct(efResult.risk_free_rate)} · long-only, sum of weights = 1
                                {#if Object.keys(efResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(efResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingEF}
                            <div class="emptyState">Click "Compute frontier" to build the Markowitz efficient frontier over the last {efLookback}, mark your portfolio on it, and read suggested weights.</div>
                        {/if}
                    </div>

                    <!-- CORRELATION MATRIX -->
                    <div class="mcSection">
                        <div class="sectionTitle">Correlation Matrix · Diversification</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={corrLookback}>
                                    <option value="6M">6 Months</option>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <button class="btn primary xsmall" on:click={runCorrelation}
                                    disabled={isFetchingCorr || !positionView || positionView.rows.length < 2}>
                                {isFetchingCorr ? "Computing…" : "Compute correlations"}
                            </button>
                        </div>

                        {#if corrError}
                            <div class="errorBox">{corrError}</div>
                        {/if}

                        {#if corrResult}
                            <div class="corrLayout">
                                <div class="corrMatrixWrap">
                                    <table class="corrMatrix">
                                        <thead>
                                        <tr>
                                            <th></th>
                                            {#each corrResult.tickers as t}
                                                <th class="corrTickerHead"><span class="mono">{t}</span></th>
                                            {/each}
                                        </tr>
                                        </thead>
                                        <tbody>
                                        {#each corrResult.tickers as rowTicker, i}
                                            <tr>
                                                <th class="corrTickerHead rowHead"><span class="mono">{rowTicker}</span></th>
                                                {#each corrResult.tickers as colTicker, j}
                                                    <td class="corrCell"
                                                        style="background: {corrCellColor(corrResult.matrix[i][j])}; color: {corrTextColor(corrResult.matrix[i][j])};"
                                                        title="{rowTicker} ↔ {colTicker}: {corrResult.matrix[i][j].toFixed(3)}">
                                                        <span class="mono">{corrResult.matrix[i][j].toFixed(2)}</span>
                                                    </td>
                                                {/each}
                                            </tr>
                                        {/each}
                                        </tbody>
                                    </table>
                                    <div class="corrLegend">
                                        <span class="corrLegendItem"><span class="corrSwatch" style="background: {corrCellColor(-1)};"></span> −1.00</span>
                                        <span class="corrLegendItem"><span class="corrSwatch" style="background: {corrCellColor(0)};"></span> 0.00</span>
                                        <span class="corrLegendItem"><span class="corrSwatch" style="background: {corrCellColor(1)};"></span> +1.00</span>
                                    </div>
                                </div>

                                <div class="corrStatsPanel">
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Diversification score</div>
                                        <div class="mcStatValue mono {corrResult.stats.diversification_score > 0.6 ? 'greenText' : corrResult.stats.diversification_score < 0.3 ? 'redText' : ''}">{formatPct(corrResult.stats.diversification_score)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Avg correlation</div>
                                        <div class="mcStatValue mono">{corrResult.stats.avg_correlation.toFixed(3)}</div>
                                    </div>
                                    {#if corrResult.stats.weighted_avg_correlation !== null}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Weighted avg (by holdings)</div>
                                            <div class="mcStatValue mono">{corrResult.stats.weighted_avg_correlation.toFixed(3)}</div>
                                        </div>
                                    {/if}
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Pairs &gt; 0.70</div>
                                        <div class="mcStatValue mono {corrResult.stats.pct_pairs_above_0_7 > 0.5 ? 'redText' : ''}">{formatPct(corrResult.stats.pct_pairs_above_0_7)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Pairs &lt; 0.30</div>
                                        <div class="mcStatValue mono {corrResult.stats.pct_pairs_below_0_3 > 0.5 ? 'greenText' : ''}">{formatPct(corrResult.stats.pct_pairs_below_0_3)}</div>
                                    </div>
                                    {#if corrResult.stats.max_pair}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Most correlated</div>
                                            <div class="mcStatValue mono redText">
                                                {corrResult.stats.max_pair.ticker_a} ↔ {corrResult.stats.max_pair.ticker_b}
                                            </div>
                                            <div class="mono soft xsmall">{corrResult.stats.max_pair.correlation.toFixed(3)}</div>
                                        </div>
                                    {/if}
                                    {#if corrResult.stats.min_pair}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Least correlated</div>
                                            <div class="mcStatValue mono greenText">
                                                {corrResult.stats.min_pair.ticker_a} ↔ {corrResult.stats.min_pair.ticker_b}
                                            </div>
                                            <div class="mono soft xsmall">{corrResult.stats.min_pair.correlation.toFixed(3)}</div>
                                        </div>
                                    {/if}
                                </div>
                            </div>

                            <div class="mcFootnote soft">
                                {corrResult.observations} daily log-return observations · {corrResult.start_date_used} → {corrResult.end_date_used} · {corrResult.stats.n_pairs} unique pairs
                                {#if Object.keys(corrResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(corrResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingCorr}
                            <div class="emptyState">Click "Compute correlations" to build the asset correlation heatmap over the last {corrLookback}.</div>
                        {/if}
                    </div>

                    <!-- MONTE CARLO SIMULATION -->
                    <div class="mcSection">
                        <div class="sectionTitle">Monte Carlo · Portfolio Trajectories</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Horizon (trading days)</span>
                                <input class="input mono xsmallInput" type="number" min="10" max="2520" step="1" bind:value={mcHorizonDays} />
                            </label>
                            <label class="field inlineField">
                                <span class="label">Simulations</span>
                                <input class="input mono xsmallInput" type="number" min="50" max="20000" step="50" bind:value={mcNSimulations} />
                            </label>
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={mcLookback}>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <button class="btn primary xsmall" on:click={runMonteCarlo} disabled={isFetchingMC || !positionView || positionView.rows.length === 0}>
                                {isFetchingMC ? "Simulating…" : "Run simulation"}
                            </button>
                        </div>

                        {#if mcError}
                            <div class="errorBox">{mcError}</div>
                        {/if}

                        {#if mcResult}
                            {@const mcData = getMonteCarloChartData(mcResult)}
                            {#if mcData}
                                <div class="mcChartWrap">
                                    <svg viewBox="0 0 {MC_W} {MC_H}" class="mcChart" preserveAspectRatio="xMidYMid meet">
                                        <defs>
                                            <linearGradient id="mc-band-outer" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stop-color="rgba(0, 212, 255, 0.18)" />
                                                <stop offset="100%" stop-color="rgba(0, 212, 255, 0.04)" />
                                            </linearGradient>
                                            <linearGradient id="mc-band-inner" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stop-color="rgba(0, 212, 255, 0.35)" />
                                                <stop offset="100%" stop-color="rgba(0, 212, 255, 0.12)" />
                                            </linearGradient>
                                        </defs>

                                        <!-- Y gridlines + labels -->
                                        {#each mcData.yTicks as tick}
                                            <line x1={MC_PAD.left} y1={tick.y} x2={MC_W - MC_PAD.right} y2={tick.y} stroke="rgba(255,255,255,0.06)" stroke-width="1" />
                                            <text x={MC_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)" font-size="10" text-anchor="end" class="mono">
                                                {tick.value.toFixed(0)}
                                            </text>
                                        {/each}

                                        <!-- Baseline (initial value) -->
                                        <line x1={MC_PAD.left} y1={mcData.baselineY} x2={MC_W - MC_PAD.right} y2={mcData.baselineY} stroke="rgba(255,255,255,0.35)" stroke-width="1" stroke-dasharray="3 3" />

                                        <!-- 5-95 percentile band -->
                                        <path d={mcData.bandOuter} fill="url(#mc-band-outer)" />
                                        <!-- 25-75 percentile band -->
                                        <path d={mcData.bandInner} fill="url(#mc-band-inner)" />

                                        <!-- Spaghetti sample paths -->
                                        {#each mcData.samplePaths as p, i}
                                            <path d={p} fill="none" stroke="rgba(0, 212, 255, 0.18)" stroke-width="0.7" />
                                        {/each}

                                        <!-- Median -->
                                        <path d={mcData.median} fill="none" stroke="rgba(0, 212, 255, 0.95)" stroke-width="2" />

                                        <!-- X-axis ticks -->
                                        {#each mcData.xTicks as tick}
                                            <line x1={tick.x} y1={MC_H - MC_PAD.bottom} x2={tick.x} y2={MC_H - MC_PAD.bottom + 4} stroke="rgba(255,255,255,0.35)" />
                                            <text x={tick.x} y={MC_H - MC_PAD.bottom + 16} fill="rgba(255,255,255,0.45)" font-size="10" text-anchor="middle" class="mono">{tick.date}</text>
                                        {/each}

                                        <!-- Legend -->
                                        <g transform="translate({MC_W - MC_PAD.right - 130}, {MC_PAD.top + 4})">
                                            <rect x="0" y="0" width="14" height="8" fill="url(#mc-band-outer)" />
                                            <text x="20" y="8" fill="rgba(255,255,255,0.65)" font-size="10" class="mono">5–95%</text>
                                            <rect x="0" y="14" width="14" height="8" fill="url(#mc-band-inner)" />
                                            <text x="20" y="22" fill="rgba(255,255,255,0.65)" font-size="10" class="mono">25–75%</text>
                                            <line x1="0" y1="32" x2="14" y2="32" stroke="rgba(0, 212, 255, 0.95)" stroke-width="2" />
                                            <text x="20" y="36" fill="rgba(255,255,255,0.65)" font-size="10" class="mono">Median</text>
                                        </g>
                                    </svg>
                                </div>

                                <div class="mcStatsGrid">
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Initial</div>
                                        <div class="mcStatValue mono">{formatNum(mcResult.stats.initial_value, 2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Expected final</div>
                                        <div class="mcStatValue mono {pnlClass(mcResult.stats.expected_final - mcResult.stats.initial_value)}">{formatNum(mcResult.stats.expected_final, 2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Median final</div>
                                        <div class="mcStatValue mono {pnlClass(mcResult.stats.p50_final - mcResult.stats.initial_value)}">{formatNum(mcResult.stats.p50_final, 2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">5% final (worst)</div>
                                        <div class="mcStatValue mono redText">{formatNum(mcResult.stats.p5_final, 2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">95% final (best)</div>
                                        <div class="mcStatValue mono greenText">{formatNum(mcResult.stats.p95_final, 2)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">P(positive)</div>
                                        <div class="mcStatValue mono">{formatPct(mcResult.stats.prob_positive)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Ann. drift</div>
                                        <div class="mcStatValue mono {pnlClass(mcResult.stats.annualized_drift)}">{formatPct(mcResult.stats.annualized_drift)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Ann. volatility</div>
                                        <div class="mcStatValue mono">{formatPct(mcResult.stats.annualized_volatility)}</div>
                                    </div>
                                </div>

                                <div class="mcFootnote soft">
                                    {mcResult.stats.n_simulations} simulations · {mcResult.stats.horizon_days} trading days · params estimated on {mcResult.stats.lookback_start} → {mcResult.stats.lookback_end}
                                    {#if Object.keys(mcResult.errors).length > 0}
                                        · Skipped tickers: {Object.keys(mcResult.errors).join(", ")}
                                    {/if}
                                </div>
                            {/if}
                        {:else if !isFetchingMC}
                            <div class="emptyState">Click "Run simulation" to project {mcHorizonDays} trading days forward using {mcNSimulations} GBM paths.</div>
                        {/if}
                    </div>
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

    .mcSection {
        margin-top: 32px;
        padding-top: 24px;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
    }

    .mcControls {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: flex-end;
        margin: 12px 0 20px 0;
    }

    .mcChartWrap {
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        margin-top: 8px;
    }

    .mcChart {
        width: 100%;
        height: auto;
        max-height: 420px;
        display: block;
    }

    .mcStatsGrid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin-top: 16px;
    }

    .mcStat {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 10px 12px;
    }

    .mcStatLabel {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: rgba(255, 255, 255, 0.5);
        margin-bottom: 4px;
    }

    .mcStatValue {
        font-size: 15px;
        font-weight: 600;
    }

    .mcFootnote {
        margin-top: 12px;
        font-size: 11px;
    }

    .corrLayout {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 280px;
        gap: 16px;
        margin-top: 8px;
        align-items: start;
    }

    @media (max-width: 1100px) {
        .corrLayout {
            grid-template-columns: 1fr;
        }
    }

    .corrMatrixWrap {
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 12px;
        overflow: auto;
        max-width: 100%;
    }

    .corrMatrix {
        border-collapse: separate;
        border-spacing: 2px;
        font-family: ui-monospace, monospace;
    }

    .corrMatrix th,
    .corrMatrix td {
        padding: 6px 8px;
        text-align: center;
        font-size: 11px;
    }

    .corrTickerHead {
        color: rgba(235, 235, 245, 0.75);
        background: rgba(255, 0, 60, 0.06);
        border-radius: 4px;
        font-weight: 600;
        white-space: nowrap;
    }

    .corrTickerHead.rowHead {
        text-align: right;
        background: rgba(255, 0, 60, 0.04);
    }

    .corrCell {
        border-radius: 4px;
        min-width: 48px;
        cursor: default;
        transition: transform 100ms ease;
    }

    .corrCell:hover {
        transform: scale(1.06);
        outline: 1px solid rgba(255, 255, 255, 0.45);
    }

    .corrLegend {
        display: flex;
        gap: 18px;
        margin-top: 12px;
        font-size: 11px;
        color: rgba(235, 235, 245, 0.6);
        font-family: ui-monospace, monospace;
    }

    .corrLegendItem {
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .corrSwatch {
        display: inline-block;
        width: 14px;
        height: 14px;
        border-radius: 3px;
        border: 1px solid rgba(255, 255, 255, 0.15);
    }

    .corrStatsPanel {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .healthHeadline {
        display: grid;
        grid-template-columns: 220px minmax(0, 1fr);
        gap: 16px;
        margin-top: 8px;
        align-items: stretch;
    }

    @media (max-width: 900px) {
        .healthHeadline {
            grid-template-columns: 1fr;
        }
    }

    .healthBigKpi {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.14), rgba(255, 0, 60, 0.04));
        border: 1px solid rgba(255, 0, 60, 0.30);
        border-radius: 12px;
        padding: 16px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
        box-shadow: inset 0 0 18px rgba(255, 0, 60, 0.12);
    }

    .healthBigLabel {
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.6);
        margin-bottom: 8px;
    }

    .healthBigValue {
        font-size: 38px;
        font-weight: 700;
        line-height: 1;
        margin-bottom: 6px;
    }

    .healthVerdict {
        font-size: 11px;
        letter-spacing: 0.10em;
        text-transform: uppercase;
    }

    .healthSubGrid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 10px;
    }

    .efChartWrap {
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        margin-top: 8px;
    }

    .efSummary {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
        margin-top: 12px;
    }

    .efWeightsGrid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
        margin-top: 16px;
    }

    @media (max-width: 900px) {
        .efWeightsGrid {
            grid-template-columns: 1fr;
        }
    }

    .efWeightsTitle {
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.6);
        margin-bottom: 6px;
        padding-left: 4px;
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
