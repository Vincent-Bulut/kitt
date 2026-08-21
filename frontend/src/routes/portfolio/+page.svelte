<script lang="ts">
    import {instance} from "$lib/axiosAPI.js";
    import {onMount} from "svelte";
    import {page} from "$app/stores";

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

    type VaREsPoint = {
        confidence_level: number;
        var_historical: number;
        es_historical: number;
        var_gaussian: number;
        es_gaussian: number;
        var_cornish_fisher: number;
        es_cf_empirical_tail: number;
    };

    type VaREsRow = {
        ticker: string;
        start_date_requested: string;
        end_date_requested: string;
        start_date_used: string;
        end_date_used: string;
        observations: number;
        return_mode: "arith" | "log";
        horizon: string;
        price_type: string;
        points: VaREsPoint[];
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

    // --- PCA / eigen risk decomposition ---
    type PCAComponent = {
        index: number;
        eigenvalue: number;
        factor_volatility: number;
        explained_variance_ratio: number;
        cumulative_explained: number;
        portfolio_exposure: number;
        variance_contribution: number;
        variance_contribution_pct: number;
        cumulative_variance_contribution_pct: number;
        risk_contribution: number;
        loadings: Record<string, number>;
        top_positive: string[];
        top_negative: string[];
        interpretation: string;
    };

    type PCAAssetRisk = {
        ticker: string;
        weight: number;
        volatility: number;
        marginal_contribution_to_risk: number;
        contribution_to_risk: number;
        contribution_to_risk_pct: number;
        pc1_loading: number;
        pc1_communality: number;
        top_component: number;
    };

    type PCAStats = {
        portfolio_volatility: number;
        portfolio_variance: number;
        total_matrix_variance: number;
        pc1_explained_ratio: number;
        pc1_variance_contribution_pct: number;
        n_components_for_80_matrix: number;
        n_components_for_90_matrix: number;
        n_components_for_90_portfolio_risk: number;
        effective_number_of_bets: number;
        max_contribution_pct: number;
        diversification_ratio: number;
        weighted_avg_volatility: number;
        condition_number: number;
    };

    type PCARiskResult = {
        tickers: string[];
        weights: number[];
        matrix_type: "covariance" | "correlation";
        return_mode: "log" | "arith";
        observations: number;
        start_date_used: string;
        end_date_used: string;
        covariance: number[][];
        matrix: number[][];
        components: PCAComponent[];
        assets: PCAAssetRisk[];
        stats: PCAStats;
        warnings: string[];
        errors: Record<string, string>;
    };

    let pcaResult: PCARiskResult | null = null;
    let pcaLookback = "3Y";
    let pcaMatrixType: "covariance" | "correlation" = "covariance";
    let pcaNComponents = 8;
    let isFetchingPCA = false;
    let pcaError = "";
    let pcaShowMatrix = false;
    let pcaSelectedPC: number | null = null;

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

    // --- Black-Litterman ---
    type BLView = {
        view_type: "absolute" | "relative";
        asset: string;
        asset_other: string | null;
        value: number;        // UI: percent (e.g. 8 = 8%)
        confidence: number;   // UI: percent (e.g. 60 = 60%)
    };

    type BLAssetPoint = {
        ticker: string;
        prior_return: number;
        posterior_return: number;
        volatility: number;
        prior_weight: number;
        optimal_weight: number;
    };

    type BlackLittermanResult = {
        tickers: string[];
        risk_free_rate: number;
        risk_aversion: number;
        tau: number;
        observations: number;
        start_date_used: string;
        end_date_used: string;
        assets: BLAssetPoint[];
        prior_weights: Record<string, number>;
        implied_returns: Record<string, number>;
        posterior_returns: Record<string, number>;
        optimal: PortfolioOnFrontier;
        min_variance: PortfolioOnFrontier;
        n_views_applied: number;
        warnings: string[];
        errors: Record<string, string>;
    };

    let blResult: BlackLittermanResult | null = null;
    let blLookback = "3Y";
    let blRf = 0.02;
    let blRiskAversion = 2.5;
    let blTau = 0.05;
    let blMaxWeight = 1.0;
    let blMinWeight = 0.0;
    let blViews: BLView[] = [];
    let isFetchingBL = false;
    let blError = "";

    type SampledPortfolio = {
        tickers: string[];
        weights: number[];
        expected_return: number;
        volatility: number;
        sharpe: number;
        avg_correlation: number;
        composite_score: number;
    };

    type SamplerCloudPoint = {
        volatility: number;
        expected_return: number;
        sharpe: number;
        avg_correlation: number;
        composite_score: number;
        tickers: string[];
        weights: number[];
    };

    type PortfolioSamplerResult = {
        universe: string[];
        portfolio_size: number;
        n_simulations_requested: number;
        n_simulations_evaluated: number;
        n_simulations_failed: number;
        observations: number;
        start_date_used: string;
        end_date_used: string;
        risk_free_rate: number;
        diversification_weight: number;
        optimization: "max_sharpe" | "equal_weight";
        top_by_composite: SampledPortfolio[];
        top_by_sharpe: SampledPortfolio[];
        cloud: SamplerCloudPoint[];
        errors: Record<string, string>;
    };

    let samplerResult: PortfolioSamplerResult | null = null;
    let samplerPortfolioSize = 5;
    let samplerNSimulations = 200;
    let samplerTopK = 5;
    let samplerLookback = "3Y";
    let samplerRf = 0.02;
    let samplerDivWeight = 1.0;
    let samplerMaxWeight = 1.0;
    let samplerMinWeight = 0.0;
    let samplerOpt: "max_sharpe" | "equal_weight" = "max_sharpe";
    let samplerSeed = 42;
    let samplerRankBy: "composite" | "sharpe" = "composite";
    let isFetchingSampler = false;
    let samplerError = "";
    let selectedSamplerPoint: SamplerCloudPoint | null = null;

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
            const next = computeFee(montant).toString();
            if (form.transaction_fee !== next) form.transaction_fee = next;
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

    // ---------------------------------------------------------------
    // VaR / ES visualization — grouped bars per ticker (one bar per
    // estimation method) at the selected confidence level, ES overlay.
    // ---------------------------------------------------------------
    let varSelectedLevel: number | null = null;

    $: varLevels = Array.from(
        new Set(riskRows.flatMap(r => r.points.map(p => p.confidence_level)))
    ).sort((a, b) => a - b);

    $: if (varLevels.length > 0 && (varSelectedLevel === null || !varLevels.includes(varSelectedLevel))) {
        varSelectedLevel = varLevels[0];
    }

    const VAR_W = 960;
    const VAR_H = 340;
    const VAR_PAD = {top: 26, right: 24, bottom: 48, left: 64};
    // Method colors validated for CVD separation on the dark chart surface
    const VAR_COLORS: Record<string, string> = {
        hist: "#2E8FB3",
        gauss: "#B08E20",
        cf: "#E0447A"
    };

    type VaRBar = {
        key: "hist" | "gauss" | "cf";
        label: string;
        x: number;
        w: number;
        y: number;
        h: number;
        v: number;
        es: number;
        esLabel: string;
    };

    function getVaRChartData(rows: VaREsRow[], level: number | null) {
        if (!rows || rows.length === 0 || level === null) return null;
        const entries = rows
            .map(r => ({ticker: r.ticker, pt: r.points.find(p => p.confidence_level === level)}))
            .filter((e): e is { ticker: string; pt: VaREsPoint } => e.pt !== undefined);
        if (entries.length === 0) return null;

        const maxVal = Math.max(
            ...entries.flatMap(e => [
                e.pt.var_historical, e.pt.var_gaussian, e.pt.var_cornish_fisher, e.pt.es_historical
            ])
        );
        const yMax = maxVal * 1.15 || 0.01;

        const innerW = VAR_W - VAR_PAD.left - VAR_PAD.right;
        const innerH = VAR_H - VAR_PAD.top - VAR_PAD.bottom;
        const baseY = VAR_PAD.top + innerH;
        const yAt = (v: number) => VAR_PAD.top + (1 - v / yMax) * innerH;

        const n = entries.length;
        const slot = innerW / n;
        const barW = Math.min(26, (slot * 0.55) / 3);

        const groups = entries.map((e, i) => {
            const cx = VAR_PAD.left + slot * (i + 0.5);
            const xs = [cx - 1.5 * barW - 2, cx - barW / 2, cx + barW / 2 + 2];
            const defs: Array<[VaRBar["key"], string, number, number, string]> = [
                ["hist", "Historical", e.pt.var_historical, e.pt.es_historical, "ES hist."],
                ["gauss", "Gaussian", e.pt.var_gaussian, e.pt.es_gaussian, "ES Gauss"],
                ["cf", "Cornish-Fisher", e.pt.var_cornish_fisher, e.pt.es_cf_empirical_tail, "ES CF tail"]
            ];
            const bars: VaRBar[] = defs.map(([key, label, v, es, esLabel], j) => ({
                key, label,
                x: xs[j],
                w: barW,
                y: yAt(v),
                h: Math.max(0, baseY - yAt(v)),
                v, es, esLabel
            }));
            return {
                ticker: e.ticker,
                cx,
                bars,
                es: e.pt.es_historical,
                esY: yAt(e.pt.es_historical),
                esX1: xs[0] - 5,
                esX2: xs[2] + barW + 5
            };
        });

        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 5; i++) {
            const v = (yMax * i) / 5;
            yTicks.push({value: v, y: yAt(v)});
        }

        return {groups, yTicks, baseY};
    }

    // ---------------------------------------------------------------
    // Asset exclusion — symbols ignored by Portfolio Health, Portfolio
    // Optimization, Black-Litterman, Diversification Analysis, Risk
    // Decomposition and Monte Carlo. Weights are renormalized by the
    // backend over the remaining tickers.
    // ---------------------------------------------------------------
    let excludedSymbols: string[] = [];

    function toggleExcludedSymbol(symbol: string) {
        excludedSymbols = excludedSymbols.includes(symbol)
            ? excludedSymbols.filter(s => s !== symbol)
            : [...excludedSymbols, symbol];
    }

    function clearExcludedSymbols() {
        excludedSymbols = [];
    }

    function includedRows(): PositionRow[] {
        if (!positionView) return [];
        return positionView.rows.filter(r => !excludedSymbols.includes(r.symbol));
    }

    // Exclusions are per-portfolio: reset them when switching portfolio
    $: if (selectedPortfolioId !== null) {
        excludedSymbols = [];
    }

    async function runMonteCarlo() {
        if (!positionView || positionView.rows.length === 0) {
            mcError = "No positions to simulate.";
            return;
        }
        const eligible = includedRows().filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length === 0) {
            mcError = excludedSymbols.length > 0
                ? "No eligible positions left after exclusions."
                : "No positions with a valid market weight.";
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
                initial_value: eligible.reduce((s, r) => s + (r.market_value ?? 0), 0)
                    || positionView.total_market_value || 1.0,
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

    async function runSampler() {
        if (!assets || assets.length < samplerPortfolioSize) {
            samplerError = `Need at least ${samplerPortfolioSize} assets in the referential.`;
            samplerResult = null;
            return;
        }
        isFetchingSampler = true;
        samplerError = "";
        selectedSamplerPoint = null;
        try {
            const payload = {
                tickers: assets.map(a => a.symbol),
                portfolio_size: samplerPortfolioSize,
                n_simulations: samplerNSimulations,
                top_k: samplerTopK,
                lookback_period: samplerLookback,
                auto_adjust: true,
                risk_free_rate: samplerRf,
                diversification_weight: samplerDivWeight,
                max_weight: samplerMaxWeight,
                min_weight: samplerMinWeight,
                optimization: samplerOpt,
                seed: samplerSeed
            };
            const res = await instance.post<PortfolioSamplerResult>("/analytics/yahoo/portfolio-sampler", payload);
            samplerResult = res.data;
        } catch (err: any) {
            samplerError = err?.response?.data?.detail || err?.message || "Unable to run portfolio sampler.";
            samplerResult = null;
        } finally {
            isFetchingSampler = false;
        }
    }

    // Sampler scatter chart geometry
    const SAMP_W = 960;
    const SAMP_H = 420;
    const SAMP_PAD = {top: 24, right: 24, bottom: 44, left: 64};

    function getSamplerChartData(r: PortfolioSamplerResult | null) {
        if (!r || r.cloud.length === 0) return null;
        const allX = r.cloud.map(p => p.volatility);
        const allY = r.cloud.map(p => p.expected_return);
        const xMin = 0;
        const xMax = Math.max(...allX) * 1.05;
        const yLo = Math.min(...allY);
        const yHi = Math.max(...allY);
        const yPad = (yHi - yLo) * 0.10 || 0.01;
        const yMin = yLo - yPad;
        const yMax = yHi + yPad;

        const innerW = SAMP_W - SAMP_PAD.left - SAMP_PAD.right;
        const innerH = SAMP_H - SAMP_PAD.top - SAMP_PAD.bottom;

        const xAt = (v: number) => SAMP_PAD.left + ((v - xMin) / (xMax - xMin || 1)) * innerW;
        const yAt = (v: number) => SAMP_PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;

        const xTicks: { value: number; x: number }[] = [];
        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 5; i++) {
            const vx = xMin + ((xMax - xMin) * i) / 5;
            xTicks.push({value: vx, x: xAt(vx)});
            const vy = yMin + ((yMax - yMin) * i) / 5;
            yTicks.push({value: vy, y: yAt(vy)});
        }
        return {xAt, yAt, xMin, xMax, yMin, yMax, xTicks, yTicks};
    }

    function selectSamplerPointOnKey(e: KeyboardEvent, pt: SamplerCloudPoint) {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            selectedSamplerPoint = pt;
        }
    }

    // Color points by correlation balance (greener = lower correlation)
    function corrPointColor(avgCorr: number, alpha: number = 0.55): string {
        const c = Math.max(-0.2, Math.min(1, avgCorr));
        // 0 -> green, 1 -> red
        const t = (c + 0.2) / 1.2; // [0..1]
        const r = Math.round(255 * t);
        const g = Math.round(180 * (1 - t) + 60 * t);
        const b = Math.round(120 * (1 - t));
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    async function runEfficientFrontier() {
        if (!positionView || positionView.rows.length < 2) {
            efError = "Need at least 2 positions to compute the frontier.";
            efResult = null;
            return;
        }
        const eligible = includedRows().filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length < 2) {
            efError = excludedSymbols.length > 0
                ? "Need at least 2 eligible positions after exclusions."
                : "Need at least 2 positions with a valid market weight.";
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
    const EF_PAD = {top: 24, right: 24, bottom: 44, left: 64};

    function getEFChartData(r: EfficientFrontierResult | null) {
        if (!r) return null;
        const allX: number[] = [];
        const allY: number[] = [];
        r.frontier.forEach(p => {
            allX.push(p.volatility);
            allY.push(p.expected_return);
        });
        r.assets.forEach(a => {
            allX.push(a.volatility);
            allY.push(a.expected_return);
        });
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
        const cml = {x1: xAt(0), y1: yAt(r.risk_free_rate), x2: xAt(cmlX2), y2: yAt(cmlY2)};

        // Y/X ticks (5)
        const xTicks: { value: number; x: number }[] = [];
        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 5; i++) {
            const vx = xMin + ((xMax - xMin) * i) / 5;
            xTicks.push({value: vx, x: xAt(vx)});
            const vy = yMin + ((yMax - yMin) * i) / 5;
            yTicks.push({value: vy, y: yAt(vy)});
        }

        return {
            xAt, yAt,
            frontierPath,
            cml,
            xTicks, yTicks,
            xMin, xMax, yMin, yMax,
        };
    }

    function blPortfolioTickers(): string[] {
        if (!positionView) return [];
        return includedRows()
            .filter(r => r.weight !== null && r.weight !== undefined && r.weight > 0)
            .map(r => r.symbol);
    }

    function addBLView() {
        const tickers = blPortfolioTickers();
        const first = tickers[0] ?? "";
        const second = tickers.find(t => t !== first) ?? null;
        blViews = [...blViews, {
            view_type: "absolute",
            asset: first,
            asset_other: second,
            value: 8,
            confidence: 60,
        }];
    }

    function removeBLView(i: number) {
        blViews = blViews.filter((_, idx) => idx !== i);
    }

    async function runBlackLitterman() {
        if (!positionView || positionView.rows.length < 2) {
            blError = "Need at least 2 positions to run Black-Litterman.";
            blResult = null;
            return;
        }
        const eligible = includedRows().filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length < 2) {
            blError = excludedSymbols.length > 0
                ? "Need at least 2 eligible positions after exclusions."
                : "Need at least 2 positions with a valid market weight.";
            blResult = null;
            return;
        }
        isFetchingBL = true;
        blError = "";
        try {
            const payload = {
                tickers: eligible.map(r => r.symbol),
                // current portfolio weights are the market/equilibrium prior
                prior_weights: eligible.map(r => r.weight as number),
                views: blViews
                    .filter(v => v.asset && (v.view_type === "absolute" || v.asset_other))
                    .filter(v =>
                        !excludedSymbols.includes(v.asset) &&
                        (v.view_type === "absolute" || !excludedSymbols.includes(v.asset_other as string))
                    )
                    .map(v => ({
                        view_type: v.view_type,
                        asset: v.asset,
                        asset_other: v.view_type === "relative" ? v.asset_other : null,
                        value: (Number(v.value) || 0) / 100,
                        confidence: Math.min(0.99, Math.max(0.01, (Number(v.confidence) || 50) / 100)),
                    })),
                lookback_period: blLookback,
                auto_adjust: true,
                risk_free_rate: blRf,
                risk_aversion: blRiskAversion,
                tau: blTau,
                max_weight: blMaxWeight,
                min_weight: blMinWeight,
            };
            const res = await instance.post<BlackLittermanResult>("/analytics/yahoo/black-litterman", payload);
            blResult = res.data;
        } catch (err: any) {
            blError = err?.response?.data?.detail || err?.message || "Unable to run Black-Litterman.";
            blResult = null;
        } finally {
            isFetchingBL = false;
        }
    }

    // Black-Litterman returns chart geometry (grouped columns: implied vs posterior)
    const BL_W = 960;
    const BL_H = 360;
    const BL_PAD = {top: 24, right: 24, bottom: 52, left: 64};

    function getBLChartData(r: BlackLittermanResult | null) {
        if (!r || r.assets.length === 0) return null;
        const vals: number[] = [];
        r.assets.forEach(a => {
            vals.push(a.prior_return, a.posterior_return);
        });
        const lo = Math.min(0, ...vals);
        const hi = Math.max(0, ...vals);
        const pad = (hi - lo) * 0.12 || 0.01;
        const yMin = lo - pad;
        const yMax = hi + pad;

        const innerW = BL_W - BL_PAD.left - BL_PAD.right;
        const innerH = BL_H - BL_PAD.top - BL_PAD.bottom;

        const yAt = (v: number) => BL_PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;
        const n = r.assets.length;
        const slot = innerW / n;
        const barW = Math.min(28, slot * 0.32);

        const groups = r.assets.map((a, i) => {
            const cx = BL_PAD.left + slot * (i + 0.5);
            return {
                ticker: a.ticker,
                cx,
                priorX: cx - barW - 2,
                postX: cx + 2,
                barW,
                prior: a.prior_return,
                posterior: a.posterior_return,
                priorY: yAt(Math.max(a.prior_return, 0)),
                priorH: Math.abs(yAt(a.prior_return) - yAt(0)),
                postY: yAt(Math.max(a.posterior_return, 0)),
                postH: Math.abs(yAt(a.posterior_return) - yAt(0)),
            };
        });

        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 5; i++) {
            const vy = yMin + ((yMax - yMin) * i) / 5;
            yTicks.push({value: vy, y: yAt(vy)});
        }

        return {yAt, groups, yTicks, zeroY: yAt(0)};
    }

    async function runPortfolioHealth() {
        if (!positionView || positionView.rows.length === 0) {
            healthError = "No positions to analyze.";
            healthResult = null;
            return;
        }
        const eligible = includedRows().filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length === 0) {
            healthError = excludedSymbols.length > 0
                ? "No eligible positions left after exclusions."
                : "No positions with a valid market weight.";
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
        const rows = includedRows();
        if (!positionView || rows.length < 2) {
            corrError = excludedSymbols.length > 0
                ? "Need at least 2 eligible positions after exclusions."
                : "Need at least 2 positions to compute correlations.";
            corrResult = null;
            return;
        }
        isFetchingCorr = true;
        corrError = "";
        try {
            const tickers = rows.map(r => r.symbol);
            const weights = rows.map(r => r.weight ?? 0);
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

    // ---------------------------------------------------------------
    // PCA — diagonalize the variance-covariance matrix, then split the
    // portfolio variance over the eigenvectors: σ²ₚ = Σ λᵢ (vᵢ'w)²
    // ---------------------------------------------------------------
    async function runPCA() {
        if (!positionView || positionView.rows.length < 2) {
            pcaError = "Need at least 2 positions to run a PCA risk decomposition.";
            pcaResult = null;
            return;
        }
        const eligible = includedRows().filter(
            r => r.weight !== null && r.weight !== undefined && r.weight > 0
        );
        if (eligible.length < 2) {
            pcaError = excludedSymbols.length > 0
                ? "Need at least 2 eligible positions after exclusions."
                : "Need at least 2 positions with a valid market weight.";
            pcaResult = null;
            return;
        }
        isFetchingPCA = true;
        pcaError = "";
        try {
            const payload = {
                tickers: eligible.map(r => r.symbol),
                weights: eligible.map(r => r.weight as number),
                lookback_period: pcaLookback,
                auto_adjust: true,
                return_mode: "log",
                matrix_type: pcaMatrixType,
                n_components: pcaNComponents,
                top_loadings: 3
            };
            const res = await instance.post<PCARiskResult>("/analytics/yahoo/pca-risk", payload);
            pcaResult = res.data;
            pcaSelectedPC = pcaResult?.components?.length ? 1 : null;
        } catch (err: any) {
            pcaError = err?.response?.data?.detail || err?.message || "Unable to run the PCA risk decomposition.";
            pcaResult = null;
        } finally {
            isFetchingPCA = false;
        }
    }

    // Variance-decomposition chart: matrix eigenvalue share vs. share of YOUR variance,
    // plus the cumulative curve of your variance.
    const PCA_W = 960;
    const PCA_H = 380;
    const PCA_PAD = {top: 28, right: 58, bottom: 64, left: 66};

    function getPCAChartData(r: PCARiskResult | null) {
        if (!r || r.components.length === 0) return null;
        const comps = r.components;
        const rawMax = Math.max(
            ...comps.map(c => Math.max(c.variance_contribution_pct, c.explained_variance_ratio))
        );
        const yMax = Math.min(1, Math.max(0.05, rawMax * 1.12));

        const innerW = PCA_W - PCA_PAD.left - PCA_PAD.right;
        const innerH = PCA_H - PCA_PAD.top - PCA_PAD.bottom;

        const yAt = (v: number) => PCA_PAD.top + (1 - v / yMax) * innerH;
        const yCum = (v: number) => PCA_PAD.top + (1 - v) * innerH;
        const baseY = PCA_PAD.top + innerH;

        const n = comps.length;
        const slot = innerW / n;
        const barW = Math.min(24, slot * 0.32);

        const bars = comps.map((c, i) => {
            const cx = PCA_PAD.left + slot * (i + 0.5);
            return {
                c,
                cx,
                mktX: cx - barW - 2,
                portX: cx + 2,
                barW,
                mktY: yAt(c.explained_variance_ratio),
                mktH: Math.max(0, baseY - yAt(c.explained_variance_ratio)),
                portY: yAt(c.variance_contribution_pct),
                portH: Math.max(0, baseY - yAt(c.variance_contribution_pct)),
                cumY: yCum(c.cumulative_variance_contribution_pct)
            };
        });

        const cumPath = bars
            .map((b, i) => `${i === 0 ? "M" : "L"}${b.cx.toFixed(2)},${b.cumY.toFixed(2)}`)
            .join(" ");

        const yTicks: { value: number; y: number }[] = [];
        for (let i = 0; i <= 4; i++) {
            const v = (yMax * i) / 4;
            yTicks.push({value: v, y: yAt(v)});
        }

        const cumTicks = [0, 0.25, 0.5, 0.75, 1].map(v => ({value: v, y: yCum(v)}));

        return {bars, cumPath, yTicks, cumTicks, baseY, yCum};
    }

    // Loadings are unit-norm, so raw magnitudes are small (≈1/√n). Normalize on the
    // largest absolute loading shown so the heatmap stays readable.
    function pcaLoadingColor(v: number, maxAbs: number): string {
        const scaled = maxAbs > 1e-9 ? Math.max(-1, Math.min(1, v / maxAbs)) : 0;
        return corrCellColor(scaled);
    }

    function pcaMaxAbsLoading(r: PCARiskResult | null): number {
        if (!r) return 1;
        let m = 0;
        r.components.forEach(c => Object.values(c.loadings).forEach(v => {
            const a = Math.abs(v);
            if (a > m) m = a;
        }));
        return m || 1;
    }

    // "How many independent bets am I really running?" — entropy-based effective
    // number of bets vs. the number of positions held.
    function pcaConcentrationClass(r: PCARiskResult): string {
        const share = r.stats.pc1_variance_contribution_pct;
        if (share >= 0.75) return "redText";
        if (share >= 0.5) return "";
        return "greenText";
    }

    function pcaVerdict(r: PCARiskResult): string {
        const s = r.stats;
        const n = r.tickers.length;
        const pc1 = s.pc1_variance_contribution_pct;
        const enb = s.effective_number_of_bets;
        const k90 = s.n_components_for_90_portfolio_risk;

        let head: string;
        if (pc1 >= 0.75) {
            head = `Highly concentrated risk: ${(pc1 * 100).toFixed(0)}% of your variance comes from a single ` +
                `principal component. Your ${n} positions behave like one bet.`;
        } else if (pc1 >= 0.5) {
            head = `Moderately concentrated: the first component carries ${(pc1 * 100).toFixed(0)}% of your variance. ` +
                `One shared driver dominates your ${n} positions.`;
        } else {
            head = `Reasonably spread: no single component exceeds ${(s.max_contribution_pct * 100).toFixed(0)}% ` +
                `of your variance across ${n} positions.`;
        }

        const bets = `You are effectively running ${enb.toFixed(1)} independent bets out of ${n} holdings, ` +
            `and ${k90} component${k90 > 1 ? "s" : ""} explain${k90 > 1 ? "" : "s"} 90% of your risk.`;

        const cond = s.condition_number > 100
            ? ` The covariance matrix is ill-conditioned (κ = ${s.condition_number.toFixed(0)}): some holdings are near-duplicates of each other.`
            : "";

        return `${head} ${bets}${cond}`;
    }

    function pcaExposureLabel(c: PCAComponent): string {
        const dir = c.portfolio_exposure >= 0 ? "long" : "short";
        return `${dir} ${Math.abs(c.portfolio_exposure).toFixed(3)}`;
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
    const CHART_PAD = {top: 10, right: 10, bottom: 20, left: 40};

    // Monte Carlo chart dimensions (full-width, taller)
    const MC_W = 960;
    const MC_H = 380;
    const MC_PAD = {top: 20, right: 60, bottom: 28, left: 70};

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
            lastVal: pts[pts.length - 1].cum_return
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
        const {percentiles, samples, stats} = result;
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
            buildLinePath(arr.map((v, i) => ({x: xAt(i), y: yAt(v)})));

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
            tickValues.push({value: v, y: yAt(v)});
        }

        const xTickCount = Math.min(6, n);
        const xTicks: { date: string; x: number }[] = [];
        for (let i = 0; i < xTickCount; i++) {
            const idx = Math.round((i / (xTickCount - 1)) * (n - 1));
            xTicks.push({date: result.dates[idx] ?? "", x: xAt(idx)});
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
                    <select class="input" bind:value={selectedPortfolioId}
                            disabled={isLoadingPortfolios || portfolios.length === 0}>
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
                        <input class="input mono" type="text" list="assetList" bind:value={form.symbol}
                               placeholder="AAPL"/>
                        <datalist id="assetList">
                            {#each assets as a}
                                <option value={a.symbol}>{a.name}</option>
                            {/each}
                        </datalist>
                    </label>
                    <label class="field">
                        <span class="label">Date</span>
                        <input class="input mono" type="date" bind:value={form.date}/>
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
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.quantity}
                               placeholder="10"/>
                    </label>
                    <label class="field">
                        <span class="label">Price</span>
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.price}
                               placeholder="180.50"/>
                    </label>
                    <label class="field">
                        <span class="label">Transaction fee</span>
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.transaction_fee}
                               on:input={() => (feeManuallyEdited = true)} placeholder="auto"/>
                    </label>
                    <label class="field">
                        <span class="label">Amount (optional)</span>
                        <input class="input mono" type="number" step="any" bind:value={form.amount}
                               placeholder="auto = qty × price"/>
                    </label>
                    <label class="field">
                        <span class="label">Currency (optional)</span>
                        <input class="input mono" type="text" maxlength="3" bind:value={form.currency}
                               placeholder="EUR"/>
                    </label>
                </div>

                {#if formError}
                    <div class="errorBox">{formError}</div>
                {/if}
                {#if formOk}
                    <div class="okBox">{formOk}</div>
                {/if}

                <div class="actions">
                    <button class="btn primary" type="button" on:click={createTransaction}
                            disabled={isCreating || selectedPortfolioId === null}>
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
                                        <td><span
                                                class="mono {pnlClass(row.realized_pnl)}">{formatNum(row.realized_pnl)}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.unrealized_pnl)}">{formatNum(row.unrealized_pnl)}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.total_pnl)}">{formatNum(row.total_pnl)}</span>
                                        </td>
                                        <td><span class="mono">{formatNum(row.total_fees)}</span></td>
                                        <td><span class="mono">{formatNum(row.estimated_ter_cost_annual)}</span></td>
                                        <td><span class="mono">{formatPct(row.contribution_to_portfolio_pnl)}</span>
                                        </td>
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
                                <input class="input mono xsmallInput" type="text" bind:value={confidenceLevels}
                                       placeholder="0.95, 0.99"/>
                                <button class="btn primary xsmall" on:click={loadAnalytics}
                                        disabled={isFetchingAnalytics}>Update
                                </button>
                            </div>
                        </label>
                        <label class="field inlineField">
                            <span class="label">Period</span>
                            <select class="input mono xsmallInput" bind:value={selectedPeriod} on:change={loadAnalytics}
                                    disabled={isFetchingAnalytics}>
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
                                        <td><span
                                                class="mono {pnlClass(row.perf['1D'])}">{formatPctPerf(row.perf['1D'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['1W'])}">{formatPctPerf(row.perf['1W'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['1M'])}">{formatPctPerf(row.perf['1M'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['YTD'])}">{formatPctPerf(row.perf['YTD'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['1Y'])}">{formatPctPerf(row.perf['1Y'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['3Y'])}">{formatPctPerf(row.perf['3Y'])}</span>
                                        </td>
                                        <td><span
                                                class="mono {pnlClass(row.perf['5Y'])}">{formatPctPerf(row.perf['5Y'])}</span>
                                        </td>
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
                                                            <td rowspan={risk.points.length}><span
                                                                    class="mono">{vol.ticker}</span></td>
                                                            <td rowspan={risk.points.length}><span
                                                                    class="mono">{formatPct(vol.annualized_volatility)}</span>
                                                            </td>
                                                        {/if}
                                                        <td><span
                                                                class="mono soft">{(pt.confidence_level * 100).toFixed(0)}
                                                            %</span></td>
                                                        <td><span class="mono">{formatPct(pt.var_historical)}</span>
                                                        </td>
                                                        <td><span class="mono">{formatPct(pt.es_historical)}</span></td>
                                                    </tr>
                                                {/each}
                                            {:else}
                                                <tr>
                                                    <td><span class="mono">{vol.ticker}</span></td>
                                                    <td><span class="mono">{formatPct(vol.annualized_volatility)}</span>
                                                    </td>
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
                                                <td><span
                                                        class="mono redText">{formatPct(dd.metrics.max_drawdown)}</span>
                                                </td>
                                                <td><span
                                                        class="mono {pnlClass(-dd.metrics.current_drawdown)}">{formatPct(dd.metrics.current_drawdown)}</span>
                                                </td>
                                            </tr>
                                        {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>

                        <!-- VALUE AT RISK — visual section -->
                        <div class="sectionTitle">Value at Risk · VaR & Expected Shortfall (1-day)</div>
                        {#if riskRows.length > 0 && varSelectedLevel !== null}
                            {@const varData = getVaRChartData(riskRows, varSelectedLevel)}
                            {#if varLevels.length > 1}
                                <div class="varLevelSwitch">
                                    <span class="label">Confidence</span>
                                    {#each varLevels as lvl}
                                        <button class="chipBtn mono" class:activeLevel={varSelectedLevel === lvl}
                                                on:click={() => (varSelectedLevel = lvl)}>
                                            {(lvl * 100).toFixed(0)}%
                                        </button>
                                    {/each}
                                </div>
                            {/if}

                            {#if varData}
                                <div class="mcChartWrap">
                                    <div class="varLegendRow">
                                        <span class="varLegendItem">
                                            <span class="varSwatch" style="background:{VAR_COLORS.hist}"></span>
                                            <span class="mono soft xsmall">VaR Historical</span>
                                        </span>
                                        <span class="varLegendItem">
                                            <span class="varSwatch" style="background:{VAR_COLORS.gauss}"></span>
                                            <span class="mono soft xsmall">VaR Gaussian</span>
                                        </span>
                                        <span class="varLegendItem">
                                            <span class="varSwatch" style="background:{VAR_COLORS.cf}"></span>
                                            <span class="mono soft xsmall">VaR Cornish-Fisher</span>
                                        </span>
                                        <span class="varLegendItem">
                                            <span class="varDash"></span>
                                            <span class="mono soft xsmall">ES (historical)</span>
                                        </span>
                                        <span class="mono soft xsmall" style="margin-left:auto">
                                            {((varSelectedLevel ?? 0) * 100).toFixed(0)}% confidence · daily loss
                                        </span>
                                    </div>
                                    <svg class="mcChart" viewBox="0 0 {VAR_W} {VAR_H}" role="img"
                                         aria-label="Daily Value at Risk by estimation method per asset at {((varSelectedLevel ?? 0) * 100).toFixed(0)}% confidence">
                                        {#each varData.yTicks as tick}
                                            <line x1={VAR_PAD.left} y1={tick.y} x2={VAR_W - VAR_PAD.right} y2={tick.y}
                                                  stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={VAR_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        {#each varData.groups as g (g.ticker)}
                                            {#each g.bars as b}
                                                <rect x={b.x} y={b.y} width={b.w} height={b.h}
                                                      fill={VAR_COLORS[b.key]}>
                                                    <title>{g.ticker} · {b.label} VaR {formatPct(b.v)} · {b.esLabel} {formatPct(b.es)}</title>
                                                </rect>
                                            {/each}
                                            <line x1={g.esX1} y1={g.esY} x2={g.esX2} y2={g.esY}
                                                  stroke="rgba(255,255,255,0.85)" stroke-width="1.5"
                                                  stroke-dasharray="4 3">
                                                <title>{g.ticker} · ES historical {formatPct(g.es)}</title>
                                            </line>
                                            <text x={g.cx} y={varData.baseY + 16} fill="rgba(255,255,255,0.65)"
                                                  font-size="11" text-anchor="middle" class="mono">{g.ticker}</text>
                                        {/each}

                                        <line x1={VAR_PAD.left} y1={varData.baseY} x2={VAR_W - VAR_PAD.right}
                                              y2={varData.baseY} stroke="rgba(255,255,255,0.35)" stroke-width="1"/>
                                    </svg>
                                </div>
                            {/if}

                            <div class="tableWrap varTableGap">
                                <table class="kittTable">
                                    <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Conf.</th>
                                        <th>VaR hist.</th>
                                        <th>ES hist.</th>
                                        <th>VaR Gauss</th>
                                        <th>ES Gauss</th>
                                        <th>VaR CF</th>
                                        <th>ES CF tail</th>
                                        <th>Obs.</th>
                                    </tr>
                                    </thead>
                                    <tbody>
                                    {#each riskRows as row (row.ticker)}
                                        {#each row.points as pt, i}
                                            <tr>
                                                {#if i === 0}
                                                    <td rowspan={row.points.length}><span
                                                            class="mono">{row.ticker}</span></td>
                                                {/if}
                                                <td><span
                                                        class="mono soft">{(pt.confidence_level * 100).toFixed(0)}%</span>
                                                </td>
                                                <td><span class="mono">{formatPct(pt.var_historical)}</span></td>
                                                <td><span class="mono">{formatPct(pt.es_historical)}</span></td>
                                                <td><span class="mono">{formatPct(pt.var_gaussian)}</span></td>
                                                <td><span class="mono">{formatPct(pt.es_gaussian)}</span></td>
                                                <td><span class="mono">{formatPct(pt.var_cornish_fisher)}</span></td>
                                                <td><span class="mono">{formatPct(pt.es_cf_empirical_tail)}</span></td>
                                                <td><span class="mono soft">{row.observations}</span></td>
                                            </tr>
                                        {/each}
                                    {/each}
                                    </tbody>
                                </table>
                            </div>
                            <div class="mcFootnote soft">
                                1-day loss estimates on daily arithmetic returns over the selected period
                                ({selectedPeriod}) · VaR = loss threshold not exceeded at the given confidence ·
                                ES = average loss beyond the VaR · enter several levels above (e.g. "0.95, 0.99")
                                to compare confidence levels
                            </div>
                        {:else}
                            <div class="emptyState">No VaR data available for the current positions.</div>
                        {/if}

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
                                                    <linearGradient id="grad-cr-{series.ticker}" x1="0" y1="0" x2="0"
                                                                    y2="1">
                                                        <stop offset="0%" stop-color="rgba(0, 212, 255, 0.2)"/>
                                                        <stop offset="100%" stop-color="rgba(0, 212, 255, 0)"/>
                                                    </linearGradient>
                                                </defs>
                                                <line x1={CHART_PAD.left} y1={crData.baselineY}
                                                      x2={CHART_W - CHART_PAD.right} y2={crData.baselineY}
                                                      stroke="rgba(255,255,255,0.1)"/>
                                                <path d={crData.area} fill="url(#grad-cr-{series.ticker})"/>
                                                <path d={crData.path} fill="none" stroke="rgba(0, 212, 255, 0.8)"
                                                      stroke-width="1.5"/>
                                                <text x="5" y="15" fill="rgba(255,255,255,0.4)"
                                                      font-size="9">{formatPct(crData.maxVal)}</text>
                                                <text x="5" y={CHART_H - CHART_PAD.bottom} fill="rgba(255,255,255,0.4)"
                                                      font-size="9">{formatPct(crData.minVal)}</text>
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
                                                <line x1={CHART_PAD.left} y1={ddData.baselineY}
                                                      x2={CHART_W - CHART_PAD.right} y2={ddData.baselineY}
                                                      stroke="rgba(255,255,255,0.1)"/>
                                                <path d={ddData.area} fill="rgba(255, 69, 58, 0.1)"/>
                                                <path d={ddData.path} fill="none" stroke="rgba(255, 69, 58, 0.6)"
                                                      stroke-width="1.2"/>
                                                <text x="5" y={CHART_H - CHART_PAD.bottom} fill="rgba(255,255,255,0.4)"
                                                      font-size="9">{formatPct(ddData.minVal)}</text>
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
                                            {#each [...dd.episodes].sort((a, b) => a.max_drawdown - b.max_drawdown).slice(0, 5) as ep}
                                                <tr>
                                                    <td><span class="mono">{ep.start_date}</span></td>
                                                    <td><span class="mono">{ep.trough_date}</span></td>
                                                    <td><span class="mono">{ep.end_date ?? "Ongoing"}</span></td>
                                                    <td><span class="mono">{ep.duration_days}d</span></td>
                                                    <td><span class="mono redText">{formatPct(ep.max_drawdown)}</span>
                                                    </td>
                                                </tr>
                                            {/each}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            {/if}
                        {/each}
                    {/if}

                    <!-- ASSET EXCLUSION FILTER -->
                    {#if positionView && positionView.rows.length > 0}
                        <div class="mcSection">
                            <div class="sectionTitle">Asset Filter · Calculation Universe</div>
                            <div class="excludeHint soft">
                                Click a symbol to exclude it from Portfolio Health, Portfolio Optimization,
                                Black-Litterman, Diversification Analysis, Risk Decomposition and Monte Carlo.
                                Weights are renormalized over the remaining assets — re-run a computation to apply.
                            </div>
                            <div class="excludeChips">
                                {#each positionView.rows as row (row.symbol)}
                                    <button
                                            class="chipBtn mono"
                                            class:excluded={excludedSymbols.includes(row.symbol)}
                                            aria-pressed={excludedSymbols.includes(row.symbol)}
                                            title={excludedSymbols.includes(row.symbol)
                                                ? `${row.symbol} is excluded — click to include`
                                                : `${row.symbol} is included — click to exclude`}
                                            on:click={() => toggleExcludedSymbol(row.symbol)}
                                    >
                                        {row.symbol}
                                    </button>
                                {/each}
                                {#if excludedSymbols.length > 0}
                                    <button class="btn ghost xsmall" on:click={clearExcludedSymbols}>
                                        Reset ({excludedSymbols.length} excluded)
                                    </button>
                                {/if}
                            </div>
                            {#if excludedSymbols.length > 0}
                                <div class="mcFootnote soft">
                                    Excluded: <span class="mono">{excludedSymbols.join(", ")}</span>
                                    · {positionView.rows.length - excludedSymbols.length} asset(s) in the calculation set
                                </div>
                            {/if}
                        </div>
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
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001"
                                       bind:value={healthRf}/>
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
                                {healthResult.observations} daily observations · {healthResult.start_date_used}
                                → {healthResult.end_date_used} · Rf = {formatPct(healthResult.risk_free_rate)}
                                annualized · fixed-weight rebalanced daily
                                {#if Object.keys(healthResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(healthResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingHealth}
                            <div class="emptyState">Click "Compute health" to assess your portfolio's risk-adjusted
                                performance over the last {healthLookback}.
                            </div>
                        {/if}
                    </div>

                    <!-- EFFICIENT FRONTIER (Markowitz) -->
                    <div class="mcSection">
                        <div class="sectionTitle">Portfolio Optimization</div>
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
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001"
                                       bind:value={efRf}/>
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
                                    <svg viewBox="0 0 {EF_W} {EF_H}" class="mcChart"
                                         preserveAspectRatio="xMidYMid meet">
                                        <!-- Y gridlines + labels -->
                                        {#each ef.yTicks as tick}
                                            <line x1={EF_PAD.left} y1={tick.y} x2={EF_W - EF_PAD.right} y2={tick.y}
                                                  stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={EF_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <!-- X gridlines + labels -->
                                        {#each ef.xTicks as tick}
                                            <line x1={tick.x} y1={EF_PAD.top} x2={tick.x} y2={EF_H - EF_PAD.bottom}
                                                  stroke="rgba(255,255,255,0.04)" stroke-width="1"/>
                                            <text x={tick.x} y={EF_H - EF_PAD.bottom + 16} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="middle" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <!-- Axis labels -->
                                        <text x={EF_W / 2} y={EF_H - 6} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle">Annualized volatility
                                        </text>
                                        <text x={14} y={EF_H / 2} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle" transform="rotate(-90 14 {EF_H / 2})">Annualized
                                            return
                                        </text>

                                        <!-- Capital Market Line -->
                                        <line x1={ef.cml.x1} y1={ef.cml.y1} x2={ef.cml.x2} y2={ef.cml.y2}
                                              stroke="rgba(255, 215, 0, 0.55)" stroke-width="1.2"
                                              stroke-dasharray="5 4"/>

                                        <!-- Efficient frontier curve -->
                                        {#if ef.frontierPath}
                                            <path d={ef.frontierPath} fill="none" stroke="rgba(0, 212, 255, 0.95)"
                                                  stroke-width="2.2"/>
                                        {/if}

                                        <!-- Individual asset points -->
                                        {#each efResult.assets as a}
                                            <g>
                                                <circle cx={ef.xAt(a.volatility)} cy={ef.yAt(a.expected_return)} r="4"
                                                        fill="rgba(235, 235, 245, 0.6)" stroke="rgba(0,0,0,0.4)"
                                                        stroke-width="0.6">
                                                    <title>{a.ticker}: vol {(a.volatility * 100).toFixed(1)}%, ret {(a.expected_return * 100).toFixed(1)}%</title>
                                                </circle>
                                                <text x={ef.xAt(a.volatility) + 7} y={ef.yAt(a.expected_return) + 3}
                                                      fill="rgba(235, 235, 245, 0.65)" font-size="10"
                                                      class="mono">{a.ticker}</text>
                                            </g>
                                        {/each}

                                        <!-- Min variance point -->
                                        <circle cx={ef.xAt(efResult.min_variance.volatility)}
                                                cy={ef.yAt(efResult.min_variance.expected_return)} r="7"
                                                fill="rgba(34, 197, 94, 0.95)" stroke="#fff" stroke-width="1.2">
                                            <title>Min variance · vol {(efResult.min_variance.volatility * 100).toFixed(2)}%, ret {(efResult.min_variance.expected_return * 100).toFixed(2)}%, Sharpe {efResult.min_variance.sharpe.toFixed(2)}</title>
                                        </circle>

                                        <!-- Max Sharpe (tangent) point -->
                                        <circle cx={ef.xAt(efResult.max_sharpe.volatility)}
                                                cy={ef.yAt(efResult.max_sharpe.expected_return)} r="7"
                                                fill="rgba(255, 215, 0, 0.95)" stroke="#fff" stroke-width="1.2">
                                            <title>Tangent / Max Sharpe · vol {(efResult.max_sharpe.volatility * 100).toFixed(2)}%, ret {(efResult.max_sharpe.expected_return * 100).toFixed(2)}%, Sharpe {efResult.max_sharpe.sharpe.toFixed(2)}</title>
                                        </circle>

                                        <!-- Current portfolio point -->
                                        {#if efResult.current_portfolio}
                                            <circle cx={ef.xAt(efResult.current_portfolio.volatility)}
                                                    cy={ef.yAt(efResult.current_portfolio.expected_return)} r="8"
                                                    fill="rgba(255, 0, 60, 0.95)" stroke="#fff" stroke-width="1.5">
                                                <title>Your portfolio · vol {(efResult.current_portfolio.volatility * 100).toFixed(2)}%, ret {(efResult.current_portfolio.expected_return * 100).toFixed(2)}%, Sharpe {efResult.current_portfolio.sharpe.toFixed(2)}</title>
                                            </circle>
                                        {/if}

                                        <!-- Legend -->
                                        <g transform="translate({EF_W - EF_PAD.right - 200}, {EF_PAD.top + 6})">
                                            <line x1="0" y1="6" x2="18" y2="6" stroke="rgba(0, 212, 255, 0.95)"
                                                  stroke-width="2.2"/>
                                            <text x="24" y="10" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Efficient frontier
                                            </text>
                                            <line x1="0" y1="22" x2="18" y2="22" stroke="rgba(255, 215, 0, 0.55)"
                                                  stroke-width="1.2" stroke-dasharray="5 4"/>
                                            <text x="24" y="26" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Capital Market Line
                                            </text>
                                            <circle cx="9" cy="38" r="5" fill="rgba(255, 215, 0, 0.95)" stroke="#fff"
                                                    stroke-width="1"/>
                                            <text x="24" y="42" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Tangent (max Sharpe)
                                            </text>
                                            <circle cx="9" cy="54" r="5" fill="rgba(34, 197, 94, 0.95)" stroke="#fff"
                                                    stroke-width="1"/>
                                            <text x="24" y="58" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Min variance
                                            </text>
                                            {#if efResult.current_portfolio}
                                                <circle cx="9" cy="70" r="6" fill="rgba(255, 0, 60, 0.95)" stroke="#fff"
                                                        stroke-width="1.2"/>
                                                <text x="24" y="74" fill="rgba(255,255,255,0.7)" font-size="10"
                                                      class="mono">Your portfolio
                                                </text>
                                            {/if}
                                            <circle cx="9" cy="86" r="4" fill="rgba(235, 235, 245, 0.6)"
                                                    stroke="rgba(0,0,0,0.4)" stroke-width="0.6"/>
                                            <text x="24" y="90" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Individual asset
                                            </text>
                                        </g>
                                    </svg>
                                </div>

                                <div class="efSummary">
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Max Sharpe (tangent)</div>
                                        <div class="mcStatValue mono greenText">{efResult.max_sharpe.sharpe.toFixed(2)}</div>
                                        <div class="mono soft xsmall">vol {formatPct(efResult.max_sharpe.volatility)} ·
                                            ret {formatPct(efResult.max_sharpe.expected_return)}</div>
                                    </div>
                                    <div class="mcStat">
                                        <div class="mcStatLabel">Min variance</div>
                                        <div class="mcStatValue mono">{efResult.min_variance.sharpe.toFixed(2)}</div>
                                        <div class="mono soft xsmall">vol {formatPct(efResult.min_variance.volatility)}
                                            · ret {formatPct(efResult.min_variance.expected_return)}</div>
                                    </div>
                                    {#if efResult.current_portfolio}
                                        {@const cur = efResult.current_portfolio}
                                        {@const gap = efResult.max_sharpe.sharpe - cur.sharpe}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Your portfolio</div>
                                            <div class="mcStatValue mono {sharpeClass(cur.sharpe)}">{cur.sharpe.toFixed(2)}</div>
                                            <div class="mono soft xsmall">vol {formatPct(cur.volatility)} ·
                                                ret {formatPct(cur.expected_return)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Sharpe gap vs tangent</div>
                                            <div class="mcStatValue mono {gap > 0.3 ? 'redText' : ''}">
                                                −{gap.toFixed(2)}</div>
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
                                                            <td><span
                                                                    class="mono {delta > 0 ? 'greenText' : delta < 0 ? 'redText' : ''}">{delta > 0 ? "+" : ""}{formatPct(delta)}</span>
                                                            </td>
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
                                                            <td><span
                                                                    class="mono {delta > 0 ? 'greenText' : delta < 0 ? 'redText' : ''}">{delta > 0 ? "+" : ""}{formatPct(delta)}</span>
                                                            </td>
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
                                {efResult.observations} daily log-return observations · {efResult.start_date_used}
                                → {efResult.end_date_used} · Rf = {formatPct(efResult.risk_free_rate)} · long-only, sum
                                of weights = 1
                                {#if Object.keys(efResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(efResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingEF}
                            <div class="emptyState">Click "Compute frontier" to build the Markowitz efficient frontier
                                over the last {efLookback}, mark your portfolio on it, and read suggested weights.
                            </div>
                        {/if}
                    </div>

                    <!-- BLACK-LITTERMAN -->
                    <div class="mcSection">
                        <div class="sectionTitle">Black-Litterman Model</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={blLookback}>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Risk-free rate</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001"
                                       bind:value={blRf}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Risk aversion δ</span>
                                <input class="input mono xsmallInput" type="number" min="0.1" max="20" step="0.1"
                                       bind:value={blRiskAversion}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">τ (tau)</span>
                                <input class="input mono xsmallInput" type="number" min="0.01" max="1" step="0.01"
                                       bind:value={blTau}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Max weight</span>
                                <input class="input mono xsmallInput" type="number" min="0.05" max="1" step="0.05"
                                       bind:value={blMaxWeight}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Min weight</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.01"
                                       bind:value={blMinWeight}/>
                            </label>
                            <button class="btn primary xsmall" on:click={runBlackLitterman}
                                    disabled={isFetchingBL || !positionView || positionView.rows.length < 2}>
                                {isFetchingBL ? "Blending…" : "Run Black-Litterman"}
                            </button>
                        </div>

                        <!-- Investor views editor -->
                        <div class="blViews">
                            <div class="blViewsHeader">
                                <span class="efWeightsTitle">Investor views</span>
                                <button class="btn ghost xsmall" on:click={addBLView}
                                        disabled={blPortfolioTickers().length < 2}>+ Add view
                                </button>
                            </div>
                            {#if blViews.length === 0}
                                <div class="mono soft xsmall">No views — the model returns the market-implied
                                    (equilibrium) portfolio. Add views to tilt the posterior returns.
                                </div>
                            {:else}
                                {#each blViews as v, i}
                                    <div class="blViewRow">
                                        <select class="input mono xsmallInput" bind:value={v.view_type}>
                                            <option value="absolute">Absolute</option>
                                            <option value="relative">Relative</option>
                                        </select>
                                        <select class="input mono xsmallInput" bind:value={v.asset}>
                                            {#each blPortfolioTickers() as t}
                                                <option value={t}>{t}</option>
                                            {/each}
                                        </select>
                                        {#if v.view_type === "relative"}
                                            <span class="mono soft xsmall">outperforms</span>
                                            <select class="input mono xsmallInput" bind:value={v.asset_other}>
                                                {#each blPortfolioTickers() as t}
                                                    <option value={t}>{t}</option>
                                                {/each}
                                            </select>
                                            <span class="mono soft xsmall">by</span>
                                        {:else}
                                            <span class="mono soft xsmall">returns</span>
                                        {/if}
                                        <label class="field inlineField">
                                            <input class="input mono xsmallInput" type="number" step="0.5"
                                                   bind:value={v.value}/>
                                            <span class="label">%</span>
                                        </label>
                                        <label class="field inlineField">
                                            <span class="label">confidence</span>
                                            <input class="input mono xsmallInput" type="number" min="1" max="99" step="1"
                                                   bind:value={v.confidence}/>
                                            <span class="label">%</span>
                                        </label>
                                        <button class="btn ghost xsmall" on:click={() => removeBLView(i)}>✕</button>
                                    </div>
                                {/each}
                            {/if}
                        </div>

                        {#if blError}
                            <div class="errorBox">{blError}</div>
                        {/if}

                        {#if blResult}
                            {#each blResult.warnings as w}
                                <div class="mono soft xsmall">⚠ {w}</div>
                            {/each}

                            {@const bl = getBLChartData(blResult)}
                            {#if bl}
                                <div class="efChartWrap">
                                    <svg viewBox="0 0 {BL_W} {BL_H}" class="mcChart"
                                         preserveAspectRatio="xMidYMid meet">
                                        <!-- Y gridlines + labels -->
                                        {#each bl.yTicks as tick}
                                            <line x1={BL_PAD.left} y1={tick.y} x2={BL_W - BL_PAD.right} y2={tick.y}
                                                  stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={BL_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <!-- Zero line -->
                                        <line x1={BL_PAD.left} y1={bl.zeroY} x2={BL_W - BL_PAD.right} y2={bl.zeroY}
                                              stroke="rgba(255,255,255,0.25)" stroke-width="1"/>

                                        <!-- Y axis label -->
                                        <text x={14} y={BL_H / 2} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle" transform="rotate(-90 14 {BL_H / 2})">Annualized
                                            return
                                        </text>

                                        <!-- Grouped bars -->
                                        {#each bl.groups as g}
                                            <rect x={g.priorX} y={g.priorY} width={g.barW} height={g.priorH}
                                                  fill="rgba(235, 235, 245, 0.45)" stroke="rgba(0,0,0,0.3)"
                                                  stroke-width="0.5">
                                                <title>{g.ticker} implied (equilibrium): {(g.prior * 100).toFixed(2)}%</title>
                                            </rect>
                                            <rect x={g.postX} y={g.postY} width={g.barW} height={g.postH}
                                                  fill="rgba(0, 212, 255, 0.9)" stroke="rgba(0,0,0,0.3)"
                                                  stroke-width="0.5">
                                                <title>{g.ticker} Black-Litterman: {(g.posterior * 100).toFixed(2)}%</title>
                                            </rect>
                                            <text x={g.cx} y={BL_H - BL_PAD.bottom + 16} fill="rgba(235,235,245,0.65)"
                                                  font-size="10" text-anchor="middle" class="mono">{g.ticker}</text>
                                        {/each}

                                        <!-- Legend -->
                                        <g transform="translate({BL_W - BL_PAD.right - 200}, {BL_PAD.top + 2})">
                                            <rect x="0" y="0" width="14" height="10" fill="rgba(235, 235, 245, 0.45)"/>
                                            <text x="20" y="9" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">
                                                Implied (equilibrium)
                                            </text>
                                            <rect x="0" y="16" width="14" height="10" fill="rgba(0, 212, 255, 0.9)"/>
                                            <text x="20" y="25" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">
                                                Black-Litterman
                                            </text>
                                        </g>
                                    </svg>
                                </div>
                            {/if}

                            <div class="efSummary">
                                <div class="mcStat">
                                    <div class="mcStatLabel">Optimal (max Sharpe)</div>
                                    <div class="mcStatValue mono greenText">{blResult.optimal.sharpe.toFixed(2)}</div>
                                    <div class="mono soft xsmall">vol {formatPct(blResult.optimal.volatility)} ·
                                        ret {formatPct(blResult.optimal.expected_return)}</div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">Min variance</div>
                                    <div class="mcStatValue mono">{blResult.min_variance.sharpe.toFixed(2)}</div>
                                    <div class="mono soft xsmall">vol {formatPct(blResult.min_variance.volatility)}
                                        · ret {formatPct(blResult.min_variance.expected_return)}</div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">Views applied</div>
                                    <div class="mcStatValue mono">{blResult.n_views_applied}</div>
                                    <div class="mono soft xsmall">δ {blResult.risk_aversion.toFixed(1)} ·
                                        τ {blResult.tau.toFixed(2)}</div>
                                </div>
                            </div>

                            <div class="efWeightsGrid">
                                <div>
                                    <div class="efWeightsTitle">Returns & optimal weights</div>
                                    <div class="tableWrap">
                                        <table class="kittTable xsmallTable">
                                            <thead>
                                            <tr>
                                                <th>Ticker</th>
                                                <th>Implied</th>
                                                <th>BL return</th>
                                                <th>Prior w</th>
                                                <th>Optimal w</th>
                                                <th>Δ</th>
                                            </tr>
                                            </thead>
                                            <tbody>
                                            {#each blResult.assets as a}
                                                {@const dRet = a.posterior_return - a.prior_return}
                                                {@const dW = a.optimal_weight - a.prior_weight}
                                                <tr>
                                                    <td><span class="mono">{a.ticker}</span></td>
                                                    <td><span class="mono soft">{formatPct(a.prior_return)}</span></td>
                                                    <td><span
                                                            class="mono {dRet > 0 ? 'greenText' : dRet < 0 ? 'redText' : ''}">{formatPct(a.posterior_return)}</span>
                                                    </td>
                                                    <td><span class="mono soft">{formatPct(a.prior_weight)}</span></td>
                                                    <td><span class="mono">{formatPct(a.optimal_weight)}</span></td>
                                                    <td><span
                                                            class="mono {dW > 0 ? 'greenText' : dW < 0 ? 'redText' : ''}">{dW > 0 ? "+" : ""}{formatPct(dW)}</span>
                                                    </td>
                                                </tr>
                                            {/each}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>

                            <div class="mcFootnote soft">
                                {blResult.observations} daily log-return observations · {blResult.start_date_used}
                                → {blResult.end_date_used} · Rf = {formatPct(blResult.risk_free_rate)} · implied returns
                                Π = Rf + δΣw · posterior blends Π with your views · long-only, weights ∈
                                [{(blMinWeight * 100).toFixed(0)}%, {(blMaxWeight * 100).toFixed(0)}%]
                                {#if Object.keys(blResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(blResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingBL}
                            <div class="emptyState">The Black-Litterman model starts from your portfolio's
                                market-implied equilibrium returns, then blends in your views to produce posterior
                                returns and an optimal allocation. Add views (optional) and click "Run
                                Black-Litterman".
                            </div>
                        {/if}
                    </div>

                    <!-- CORRELATION MATRIX -->
                    <div class="mcSection">
                        <div class="sectionTitle">Diversification Analysis</div>
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
                                                <th class="corrTickerHead rowHead"><span class="mono">{rowTicker}</span>
                                                </th>
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
                                        <span class="corrLegendItem"><span class="corrSwatch"
                                                                           style="background: {corrCellColor(-1)};"></span> −1.00</span>
                                        <span class="corrLegendItem"><span class="corrSwatch"
                                                                           style="background: {corrCellColor(0)};"></span> 0.00</span>
                                        <span class="corrLegendItem"><span class="corrSwatch"
                                                                           style="background: {corrCellColor(1)};"></span> +1.00</span>
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
                                                {corrResult.stats.max_pair.ticker_a}
                                                ↔ {corrResult.stats.max_pair.ticker_b}
                                            </div>
                                            <div class="mono soft xsmall">{corrResult.stats.max_pair.correlation.toFixed(3)}</div>
                                        </div>
                                    {/if}
                                    {#if corrResult.stats.min_pair}
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Least correlated</div>
                                            <div class="mcStatValue mono greenText">
                                                {corrResult.stats.min_pair.ticker_a}
                                                ↔ {corrResult.stats.min_pair.ticker_b}
                                            </div>
                                            <div class="mono soft xsmall">{corrResult.stats.min_pair.correlation.toFixed(3)}</div>
                                        </div>
                                    {/if}
                                </div>
                            </div>

                            <div class="mcFootnote soft">
                                {corrResult.observations} daily log-return observations · {corrResult.start_date_used}
                                → {corrResult.end_date_used} · {corrResult.stats.n_pairs} unique pairs
                                {#if Object.keys(corrResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(corrResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingCorr}
                            <div class="emptyState">Click "Compute correlations" to build the asset correlation heatmap
                                over the last {corrLookback}.
                            </div>
                        {/if}
                    </div>

                    <!-- PCA RISK DECOMPOSITION -->
                    <div class="mcSection">
                        <div class="sectionTitle">Risk Decomposition — PCA on the Variance-Covariance Matrix</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={pcaLookback}>
                                    <option value="6M">6 Months</option>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Diagonalize</span>
                                <select class="input mono xsmallInput" bind:value={pcaMatrixType}>
                                    <option value="covariance">Covariance (Σ)</option>
                                    <option value="correlation">Correlation (R)</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Components</span>
                                <input class="input mono xsmallInput" type="number" min="1" max="30" step="1"
                                       bind:value={pcaNComponents}/>
                            </label>
                            <button class="btn primary xsmall" on:click={runPCA}
                                    disabled={isFetchingPCA || !positionView || positionView.rows.length < 2}>
                                {isFetchingPCA ? "Diagonalizing…" : "Decompose risk"}
                            </button>
                            {#if pcaResult}
                                <button class="btn ghost xsmall" on:click={() => (pcaShowMatrix = !pcaShowMatrix)}>
                                    {pcaShowMatrix ? "Hide Σ matrix" : "Show Σ matrix"}
                                </button>
                            {/if}
                        </div>

                        {#if pcaError}
                            <div class="errorBox">{pcaError}</div>
                        {/if}

                        {#if pcaResult}
                            {#each pcaResult.warnings as w}
                                <div class="mono soft xsmall">⚠ {w}</div>
                            {/each}

                            <!-- Plain-language read of where the risk actually sits -->
                            <div class="pcaVerdict {pcaConcentrationClass(pcaResult)}">
                                {pcaVerdict(pcaResult)}
                            </div>

                            <div class="mcStatsGrid">
                                <div class="mcStat">
                                    <div class="mcStatLabel">Portfolio volatility</div>
                                    <div class="mcStatValue mono">{formatPct(pcaResult.stats.portfolio_volatility)}</div>
                                    <div class="mono soft xsmall">σ²ₚ
                                        = {pcaResult.stats.portfolio_variance.toFixed(5)}</div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">PC1 share of your risk</div>
                                    <div class="mcStatValue mono {pcaConcentrationClass(pcaResult)}">
                                        {formatPct(pcaResult.stats.pc1_variance_contribution_pct)}
                                    </div>
                                    <div class="mono soft xsmall">
                                        {formatPct(pcaResult.stats.pc1_explained_ratio)} of matrix variance
                                    </div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">Effective nb of bets</div>
                                    <div class="mcStatValue mono {pcaResult.stats.effective_number_of_bets < 2 ? 'redText' : pcaResult.stats.effective_number_of_bets > 4 ? 'greenText' : ''}">
                                        {formatNum(pcaResult.stats.effective_number_of_bets, 2)}
                                    </div>
                                    <div class="mono soft xsmall">of {pcaResult.tickers.length} holdings</div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">PCs for 90% of your risk</div>
                                    <div class="mcStatValue mono">{pcaResult.stats.n_components_for_90_portfolio_risk}</div>
                                    <div class="mono soft xsmall">
                                        matrix needs {pcaResult.stats.n_components_for_90_matrix}
                                    </div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">Diversification ratio</div>
                                    <div class="mcStatValue mono {pcaResult.stats.diversification_ratio > 1.3 ? 'greenText' : pcaResult.stats.diversification_ratio < 1.1 ? 'redText' : ''}">
                                        {formatNum(pcaResult.stats.diversification_ratio, 3)}
                                    </div>
                                    <div class="mono soft xsmall">Σwᵢσᵢ /
                                        σₚ = {formatPct(pcaResult.stats.weighted_avg_volatility)}</div>
                                </div>
                                <div class="mcStat">
                                    <div class="mcStatLabel">Condition number κ</div>
                                    <div class="mcStatValue mono {pcaResult.stats.condition_number > 100 ? 'redText' : ''}">
                                        {formatNum(pcaResult.stats.condition_number, 1)}
                                    </div>
                                    <div class="mono soft xsmall">λmax / λmin</div>
                                </div>
                            </div>

                            {@const pca = getPCAChartData(pcaResult)}
                            {#if pca}
                                <div class="efChartWrap">
                                    <svg viewBox="0 0 {PCA_W} {PCA_H}" class="mcChart"
                                         preserveAspectRatio="xMidYMid meet">
                                        <!-- Left axis: share of variance -->
                                        {#each pca.yTicks as tick}
                                            <line x1={PCA_PAD.left} y1={tick.y} x2={PCA_W - PCA_PAD.right} y2={tick.y}
                                                  stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={PCA_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(0)}%
                                            </text>
                                        {/each}

                                        <!-- Right axis: cumulative share of portfolio variance -->
                                        {#each pca.cumTicks as tick}
                                            <text x={PCA_W - PCA_PAD.right + 8} y={tick.y + 3}
                                                  fill="rgba(0,212,255,0.5)" font-size="10" text-anchor="start"
                                                  class="mono">
                                                {(tick.value * 100).toFixed(0)}%
                                            </text>
                                        {/each}

                                        <text x={16} y={PCA_H / 2} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle" transform="rotate(-90 16 {PCA_H / 2})">
                                            Share of variance
                                        </text>
                                        <text x={PCA_W - 12} y={PCA_H / 2} fill="rgba(0,212,255,0.55)" font-size="11"
                                              text-anchor="middle" transform="rotate(90 {PCA_W - 12} {PCA_H / 2})">
                                            Cumulative (your risk)
                                        </text>

                                        <!-- 90% reference on the cumulative axis -->
                                        <line x1={PCA_PAD.left} y1={pca.yCum(0.9)} x2={PCA_W - PCA_PAD.right}
                                              y2={pca.yCum(0.9)} stroke="rgba(255,255,255,0.18)" stroke-width="1"
                                              stroke-dasharray="3 4"/>

                                        <!-- Grouped bars: eigenvalue weight in the matrix vs. in YOUR portfolio -->
                                        {#each pca.bars as b}
                                            <g class="pcaBarGroup"
                                               on:click={() => (pcaSelectedPC = b.c.index)}
                                               on:keydown={(e) => { if (e.key === "Enter") pcaSelectedPC = b.c.index; }}
                                               role="button" tabindex="0">
                                                {#if pcaSelectedPC === b.c.index}
                                                    <rect x={b.cx - b.barW - 6} y={PCA_PAD.top}
                                                          width={b.barW * 2 + 12} height={pca.baseY - PCA_PAD.top}
                                                          fill="rgba(0,212,255,0.06)" rx="3"/>
                                                {/if}
                                                <rect x={b.mktX} y={b.mktY} width={b.barW} height={b.mktH}
                                                      fill="rgba(235, 235, 245, 0.35)" stroke="rgba(0,0,0,0.3)"
                                                      stroke-width="0.5" rx="1">
                                                    <title>PC{b.c.index} eigenvalue λ = {b.c.eigenvalue.toFixed(5)} → {(b.c.explained_variance_ratio * 100).toFixed(2)}% of the matrix variance</title>
                                                </rect>
                                                <rect x={b.portX} y={b.portY} width={b.barW} height={b.portH}
                                                      fill="rgba(0, 212, 255, 0.9)" stroke="rgba(0,0,0,0.3)"
                                                      stroke-width="0.5" rx="1">
                                                    <title>PC{b.c.index} contributes {(b.c.variance_contribution_pct * 100).toFixed(2)}% of YOUR portfolio variance (λ·y² = {b.c.variance_contribution.toFixed(6)})</title>
                                                </rect>
                                                <text x={b.cx} y={PCA_H - PCA_PAD.bottom + 16}
                                                      fill={pcaSelectedPC === b.c.index ? "rgba(0,212,255,0.95)" : "rgba(235,235,245,0.65)"}
                                                      font-size="10" text-anchor="middle" class="mono">
                                                    PC{b.c.index}
                                                </text>
                                                <text x={b.cx} y={PCA_H - PCA_PAD.bottom + 30}
                                                      fill="rgba(255,255,255,0.35)" font-size="9" text-anchor="middle"
                                                      class="mono">
                                                    {formatPct(b.c.factor_volatility)}
                                                </text>
                                            </g>
                                        {/each}

                                        <!-- Cumulative curve of YOUR variance -->
                                        <path d={pca.cumPath} fill="none" stroke="rgba(0,212,255,0.75)"
                                              stroke-width="1.5" stroke-dasharray="5 3"/>
                                        {#each pca.bars as b}
                                            <circle cx={b.cx} cy={b.cumY} r="3" fill="rgba(0,212,255,0.95)">
                                                <title>Cumulative through PC{b.c.index}: {(b.c.cumulative_variance_contribution_pct * 100).toFixed(2)}% of your variance</title>
                                            </circle>
                                        {/each}

                                        <!-- Baseline -->
                                        <line x1={PCA_PAD.left} y1={pca.baseY} x2={PCA_W - PCA_PAD.right}
                                              y2={pca.baseY} stroke="rgba(255,255,255,0.25)" stroke-width="1"/>

                                        <!-- Legend -->
                                        <g transform="translate({PCA_PAD.left + 8}, {PCA_PAD.top - 18})">
                                            <rect x="0" y="0" width="14" height="10"
                                                  fill="rgba(235, 235, 245, 0.35)"/>
                                            <text x="20" y="9" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">
                                                Eigenvalue share of Σ
                                            </text>
                                            <rect x="180" y="0" width="14" height="10" fill="rgba(0, 212, 255, 0.9)"/>
                                            <text x="200" y="9" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">
                                                Share of YOUR variance
                                            </text>
                                            <line x1="370" y1="5" x2="392" y2="5" stroke="rgba(0,212,255,0.75)"
                                                  stroke-width="1.5" stroke-dasharray="5 3"/>
                                            <text x="398" y="9" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">
                                                Cumulative
                                            </text>
                                        </g>
                                    </svg>
                                </div>
                                <div class="mono soft xsmall pcaChartHint">
                                    A tall grey bar with a short cyan bar means a large eigenvalue your weights barely
                                    touch — a market risk you are already netting out. Tall cyan = risk you actually
                                    carry. Click a component to inspect its loadings.
                                </div>
                            {/if}

                            <!-- Eigenvalue table -->
                            <div class="efWeightsTitle pcaBlockTitle">Eigenvalues & contribution to portfolio variance
                            </div>
                            <div class="tableWrap">
                                <table class="kittTable xsmallTable">
                                    <thead>
                                    <tr>
                                        <th>PC</th>
                                        <th>λ (eigenvalue)</th>
                                        <th>Factor vol √λ</th>
                                        <th>% of Σ</th>
                                        <th>Exposure vᵢ'w</th>
                                        <th>λ·y² (variance)</th>
                                        <th>% of your var</th>
                                        <th>Cumul.</th>
                                        <th>What it is</th>
                                    </tr>
                                    </thead>
                                    <tbody>
                                    {#each pcaResult.components as c}
                                        <tr class="pcaRow {pcaSelectedPC === c.index ? 'pcaRowActive' : ''}"
                                            on:click={() => (pcaSelectedPC = c.index)}>
                                            <td><span class="mono">PC{c.index}</span></td>
                                            <td><span class="mono">{c.eigenvalue.toFixed(5)}</span></td>
                                            <td><span class="mono soft">{formatPct(c.factor_volatility)}</span></td>
                                            <td><span class="mono soft">{formatPct(c.explained_variance_ratio)}</span>
                                            </td>
                                            <td><span
                                                    class="mono {c.portfolio_exposure >= 0 ? '' : 'redText'}">{c.portfolio_exposure >= 0 ? "+" : ""}{c.portfolio_exposure.toFixed(4)}</span>
                                            </td>
                                            <td><span class="mono soft">{c.variance_contribution.toFixed(6)}</span></td>
                                            <td>
                                                <div class="riskBarCell">
                                                    <div class="riskBarTrack">
                                                        <div class="riskBarFill"
                                                             style="width: {Math.min(100, c.variance_contribution_pct * 100)}%"></div>
                                                    </div>
                                                    <span class="mono {c.variance_contribution_pct > 0.5 ? 'redText' : ''}">{formatPct(c.variance_contribution_pct)}</span>
                                                </div>
                                            </td>
                                            <td><span
                                                    class="mono soft">{formatPct(c.cumulative_variance_contribution_pct)}</span>
                                            </td>
                                            <td><span class="pcaInterp">{c.interpretation}</span></td>
                                        </tr>
                                    {/each}
                                    </tbody>
                                </table>
                            </div>

                            <!-- Selected component: eigenvector loadings -->
                            {@const sel = pcaResult.components.find(c => c.index === pcaSelectedPC)}
                            {#if sel}
                                {@const selMax = Math.max(...Object.values(sel.loadings).map(v => Math.abs(v)), 1e-9)}
                                <div class="pcaDetail">
                                    <div class="efWeightsTitle">Eigenvector PC{sel.index} — who loads on this risk
                                        factor
                                    </div>
                                    <div class="mono soft xsmall pcaDetailMeta">
                                        λ = {sel.eigenvalue.toFixed(5)} · factor vol {formatPct(sel.factor_volatility)}
                                        · your exposure {pcaExposureLabel(sel)} ·
                                        drives {formatPct(sel.variance_contribution_pct)} of your variance
                                    </div>
                                    <div class="pcaLoadings">
                                        {#each pcaResult.tickers as t}
                                            {@const v = sel.loadings[t] ?? 0}
                                            {@const half = (Math.abs(v) / selMax) * 50}
                                            <div class="pcaLoadRow">
                                                <span class="pcaLoadTicker mono">{t}</span>
                                                <div class="pcaLoadTrack">
                                                    <div class="pcaLoadCenter"></div>
                                                    <div class="pcaLoadFill"
                                                         style="left: {v >= 0 ? 50 : 50 - half}%; width: {half}%; background: {v >= 0 ? 'rgba(0,212,255,0.75)' : 'rgba(255,0,60,0.7)'}"></div>
                                                </div>
                                                <span class="pcaLoadVal mono {v >= 0 ? '' : 'redText'}">{v >= 0 ? "+" : ""}{v.toFixed(3)}</span>
                                            </div>
                                        {/each}
                                    </div>
                                </div>
                            {/if}

                            <!-- Full loadings heatmap -->
                            {@const maxAbs = pcaMaxAbsLoading(pcaResult)}
                            <div class="efWeightsTitle pcaBlockTitle">Loadings heatmap — assets × principal components
                            </div>
                            <div class="corrMatrixWrap">
                                <table class="corrMatrix">
                                    <thead>
                                    <tr>
                                        <th></th>
                                        {#each pcaResult.components as c}
                                            <th class="corrTickerHead">
                                                <span class="mono">PC{c.index}</span>
                                            </th>
                                        {/each}
                                    </tr>
                                    <tr>
                                        <th class="corrTickerHead rowHead"><span class="mono xsmall">% your var</span>
                                        </th>
                                        {#each pcaResult.components as c}
                                            <th>
                                                <span class="mono soft xsmall">{(c.variance_contribution_pct * 100).toFixed(1)}%</span>
                                            </th>
                                        {/each}
                                    </tr>
                                    </thead>
                                    <tbody>
                                    {#each pcaResult.tickers as t}
                                        <tr>
                                            <th class="corrTickerHead rowHead"><span class="mono">{t}</span></th>
                                            {#each pcaResult.components as c}
                                                {@const v = c.loadings[t] ?? 0}
                                                <td class="corrCell"
                                                    style="background: {pcaLoadingColor(v, maxAbs)}; color: {corrTextColor(v / maxAbs)};"
                                                    title="{t} on PC{c.index}: {v.toFixed(4)}">
                                                    <span class="mono">{v.toFixed(2)}</span>
                                                </td>
                                            {/each}
                                        </tr>
                                    {/each}
                                    </tbody>
                                </table>
                                <div class="corrLegend">
                                    <span class="corrLegendItem"><span class="corrSwatch"
                                                                       style="background: {corrCellColor(-1)};"></span> negative loading</span>
                                    <span class="corrLegendItem"><span class="corrSwatch"
                                                                       style="background: {corrCellColor(0)};"></span> ~0</span>
                                    <span class="corrLegendItem"><span class="corrSwatch"
                                                                       style="background: {corrCellColor(1)};"></span> positive loading</span>
                                    <span class="corrLegendItem">scaled on max |loading|
                                        = {maxAbs.toFixed(3)}</span>
                                </div>
                            </div>

                            <!-- Per-asset risk attribution -->
                            <div class="efWeightsTitle pcaBlockTitle">Where the risk sits, position by position</div>
                            <div class="tableWrap">
                                <table class="kittTable xsmallTable">
                                    <thead>
                                    <tr>
                                        <th>Ticker</th>
                                        <th>Weight</th>
                                        <th>Volatility</th>
                                        <th>Marginal risk</th>
                                        <th>Risk contribution</th>
                                        <th>% of portfolio risk</th>
                                        <th>PC1 loading</th>
                                        <th>PC1 explains</th>
                                        <th>Main PC</th>
                                    </tr>
                                    </thead>
                                    <tbody>
                                    {#each [...pcaResult.assets].sort((a, b) => b.contribution_to_risk_pct - a.contribution_to_risk_pct) as a}
                                        <tr>
                                            <td><span class="mono">{a.ticker}</span></td>
                                            <td><span class="mono soft">{formatPct(a.weight)}</span></td>
                                            <td><span class="mono">{formatPct(a.volatility)}</span></td>
                                            <td><span class="mono soft">{formatPct(a.marginal_contribution_to_risk)}</span>
                                            </td>
                                            <td><span class="mono">{formatPct(a.contribution_to_risk)}</span></td>
                                            <td>
                                                <div class="riskBarCell">
                                                    <div class="riskBarTrack">
                                                        <div class="riskBarFill"
                                                             style="width: {Math.min(100, Math.max(0, a.contribution_to_risk_pct * 100))}%"></div>
                                                    </div>
                                                    <span class="mono {a.contribution_to_risk_pct > a.weight * 1.25 ? 'redText' : a.contribution_to_risk_pct < a.weight * 0.75 ? 'greenText' : ''}">
                                                        {formatPct(a.contribution_to_risk_pct)}
                                                    </span>
                                                </div>
                                            </td>
                                            <td><span
                                                    class="mono {a.pc1_loading >= 0 ? '' : 'redText'}">{a.pc1_loading >= 0 ? "+" : ""}{a.pc1_loading.toFixed(3)}</span>
                                            </td>
                                            <td><span
                                                    class="mono soft">{formatPct(a.pc1_communality)}</span></td>
                                            <td><span class="mono">PC{a.top_component}</span></td>
                                        </tr>
                                    {/each}
                                    </tbody>
                                </table>
                            </div>
                            <div class="mono soft xsmall pcaChartHint">
                                Green in "% of portfolio risk" = the position carries less risk than its weight
                                (a diversifier); red = it carries more risk than its weight. Risk contributions sum
                                to the portfolio volatility {formatPct(pcaResult.stats.portfolio_volatility)}.
                            </div>

                            <!-- Raw variance-covariance matrix -->
                            {#if pcaShowMatrix}
                                {@const covMax = Math.max(...pcaResult.covariance.flat().map(v => Math.abs(v)), 1e-12)}
                                <div class="efWeightsTitle pcaBlockTitle">Annualized variance-covariance matrix Σ</div>
                                <div class="corrMatrixWrap">
                                    <table class="corrMatrix">
                                        <thead>
                                        <tr>
                                            <th></th>
                                            {#each pcaResult.tickers as t}
                                                <th class="corrTickerHead"><span class="mono">{t}</span></th>
                                            {/each}
                                        </tr>
                                        </thead>
                                        <tbody>
                                        {#each pcaResult.tickers as rowTicker, i}
                                            <tr>
                                                <th class="corrTickerHead rowHead"><span
                                                        class="mono">{rowTicker}</span></th>
                                                {#each pcaResult.tickers as colTicker, j}
                                                    <td class="corrCell"
                                                        style="background: {pcaLoadingColor(pcaResult.covariance[i][j], covMax)}; color: {corrTextColor(pcaResult.covariance[i][j] / covMax)};"
                                                        title="cov({rowTicker}, {colTicker}) = {pcaResult.covariance[i][j].toFixed(6)}{i === j ? ` → vol ${(Math.sqrt(Math.max(pcaResult.covariance[i][j], 0)) * 100).toFixed(2)}%` : ''}">
                                                        <span class="mono">{(pcaResult.covariance[i][j] * 1000).toFixed(2)}</span>
                                                    </td>
                                                {/each}
                                            </tr>
                                        {/each}
                                        </tbody>
                                    </table>
                                    <div class="corrLegend">
                                        <span class="corrLegendItem">values ×1000 · diagonal = variance (σᵢ²)</span>
                                        <span class="corrLegendItem">trace
                                            = {pcaResult.stats.total_matrix_variance.toFixed(5)}</span>
                                    </div>
                                </div>
                            {/if}

                            <div class="mcFootnote soft">
                                {pcaResult.observations} daily log-return
                                observations · {pcaResult.start_date_used}
                                → {pcaResult.end_date_used} · diagonalized
                                the {pcaResult.matrix_type === "covariance" ? "covariance matrix Σ" : "correlation matrix R"}
                                of {pcaResult.tickers.length} holdings · Σ = VΛV′ with V orthonormal, so
                                σ²ₚ = w′Σw = Σᵢ λᵢ (vᵢ′w)² — each bar is one exact, additive slice of your variance
                                {#if pcaResult.matrix_type === "correlation"}
                                    (weights vol-scaled by w̃ = Dw so the identity still holds exactly)
                                {/if}
                                {#if Object.keys(pcaResult.errors).length > 0}
                                    · Skipped tickers: {Object.keys(pcaResult.errors).join(", ")}
                                {/if}
                            </div>
                        {:else if !isFetchingPCA}
                            <div class="emptyState">Diagonalizes your portfolio's variance-covariance matrix into
                                orthogonal risk factors (principal components) and splits your variance exactly across
                                them: σ²ₚ = Σᵢ λᵢ (vᵢ′w)². A big eigenvalue only hurts if your weights are exposed to
                                it — this tells you which components actually drive your risk, which holdings load on
                                them, and how many independent bets you are really running. Click "Decompose risk".
                            </div>
                        {/if}
                    </div>

                    <!-- RANDOM PORTFOLIO SAMPLER -->
                    <div class="mcSection">
                        <div class="sectionTitle">Portfolio Discovery</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Portfolio size</span>
                                <input class="input mono xsmallInput" type="number" min="2" max="20" step="1"
                                       bind:value={samplerPortfolioSize}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Simulations</span>
                                <input class="input mono xsmallInput" type="number" min="10" max="5000" step="10"
                                       bind:value={samplerNSimulations}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Top-K</span>
                                <input class="input mono xsmallInput" type="number" min="1" max="50" step="1"
                                       bind:value={samplerTopK}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Lookback</span>
                                <select class="input mono xsmallInput" bind:value={samplerLookback}>
                                    <option value="1Y">1 Year</option>
                                    <option value="2Y">2 Years</option>
                                    <option value="3Y">3 Years</option>
                                    <option value="5Y">5 Years</option>
                                    <option value="10Y">10 Years</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Risk-free rate</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.001"
                                       bind:value={samplerRf}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Diversification λ</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="5" step="0.05"
                                       bind:value={samplerDivWeight}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Max weight</span>
                                <input class="input mono xsmallInput" type="number" min="0.05" max="1" step="0.05"
                                       bind:value={samplerMaxWeight}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Min weight</span>
                                <input class="input mono xsmallInput" type="number" min="0" max="0.5" step="0.01"
                                       bind:value={samplerMinWeight}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Weighting</span>
                                <select class="input mono xsmallInput" bind:value={samplerOpt}>
                                    <option value="max_sharpe">Max Sharpe (Markowitz)</option>
                                    <option value="equal_weight">Equal weight (1/N)</option>
                                </select>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Seed</span>
                                <input class="input mono xsmallInput" type="number" step="1" bind:value={samplerSeed}/>
                            </label>
                            <button class="btn primary xsmall" on:click={runSampler}
                                    disabled={isFetchingSampler || !assets || assets.length < samplerPortfolioSize}>
                                {isFetchingSampler ? "Sampling…" : "Run sampler"}
                            </button>
                        </div>

                        <div class="soft xsmall mono" style="margin-bottom: 6px;">
                            Universe: {assets.length} asset(s) from referential · score = sharpe − λ × avg_correlation · weight per asset ∈ [{(samplerMinWeight * 100).toFixed(0)}%, {(samplerMaxWeight * 100).toFixed(0)}%]
                        </div>

                        {#if samplerError}
                            <div class="errorBox">{samplerError}</div>
                        {/if}

                        {#if samplerResult}
                            {@const samp = getSamplerChartData(samplerResult)}
                            {@const
                                topList = samplerRankBy === "composite" ? samplerResult.top_by_composite : samplerResult.top_by_sharpe}
                            {@const topSet = new Set(topList.map(p => p.tickers.join("|") + ":" + p.sharpe.toFixed(6)))}
                            {#if samp}
                                <div class="efChartWrap">
                                    <svg viewBox="0 0 {SAMP_W} {SAMP_H}" class="mcChart"
                                         preserveAspectRatio="xMidYMid meet">
                                        {#each samp.yTicks as tick}
                                            <line x1={SAMP_PAD.left} y1={tick.y} x2={SAMP_W - SAMP_PAD.right}
                                                  y2={tick.y} stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={SAMP_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}
                                        {#each samp.xTicks as tick}
                                            <line x1={tick.x} y1={SAMP_PAD.top} x2={tick.x}
                                                  y2={SAMP_H - SAMP_PAD.bottom} stroke="rgba(255,255,255,0.04)"
                                                  stroke-width="1"/>
                                            <text x={tick.x} y={SAMP_H - SAMP_PAD.bottom + 16}
                                                  fill="rgba(255,255,255,0.45)" font-size="10" text-anchor="middle"
                                                  class="mono">
                                                {(tick.value * 100).toFixed(1)}%
                                            </text>
                                        {/each}

                                        <text x={SAMP_W / 2} y={SAMP_H - 6} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle">Annualized volatility
                                        </text>
                                        <text x={14} y={SAMP_H / 2} fill="rgba(255,255,255,0.55)" font-size="11"
                                              text-anchor="middle" transform="rotate(-90 14 {SAMP_H / 2})">Annualized
                                            return
                                        </text>

                                        <!-- Cloud (all simulated portfolios), colored by avg correlation -->
                                        {#each samplerResult.cloud as pt}
                                            <circle cx={samp.xAt(pt.volatility)} cy={samp.yAt(pt.expected_return)} r="4"
                                                    fill={corrPointColor(pt.avg_correlation, 0.55)}
                                                    class="clickablePoint"
                                                    role="button" tabindex="0"
                                                    aria-label="Portfolio: Sharpe {pt.sharpe.toFixed(2)}, correlation {pt.avg_correlation.toFixed(2)}"
                                                    on:click={() => (selectedSamplerPoint = pt)}
                                                    on:keydown={(e) => selectSamplerPointOnKey(e, pt)}>
                                                <title>vol {(pt.volatility * 100).toFixed(2)}% · ret {(pt.expected_return * 100).toFixed(2)}% · Sharpe {pt.sharpe.toFixed(2)} · avg ρ {pt.avg_correlation.toFixed(2)} — click for composition</title>
                                            </circle>
                                        {/each}

                                        <!-- Top-K highlighted -->
                                        {#each topList as p, i}
                                            <circle cx={samp.xAt(p.volatility)} cy={samp.yAt(p.expected_return)} r="8"
                                                    fill="rgba(255, 215, 0, 0.95)" stroke="#0a0a12" stroke-width="1.5"
                                                    class="clickablePoint"
                                                    role="button" tabindex="0"
                                                    aria-label="Top portfolio #{i+1}: {p.tickers.join(', ')}"
                                                    on:click={() => (selectedSamplerPoint = p)}
                                                    on:keydown={(e) => selectSamplerPointOnKey(e, p)}>
                                                <title>#{i + 1} · {p.tickers.join(", ")} · Sharpe {p.sharpe.toFixed(2)} · avg ρ {p.avg_correlation.toFixed(2)} · score {p.composite_score.toFixed(2)} — click for composition</title>
                                            </circle>
                                            <text x={samp.xAt(p.volatility)} y={samp.yAt(p.expected_return) - 11}
                                                  fill="rgba(255, 215, 0, 0.95)" font-size="11" font-weight="700"
                                                  text-anchor="middle" class="mono"
                                                  style="pointer-events: none;">#{i + 1}</text>
                                        {/each}

                                        <!-- Selected point highlight ring (rendered on top) -->
                                        {#if selectedSamplerPoint}
                                            <circle cx={samp.xAt(selectedSamplerPoint.volatility)}
                                                    cy={samp.yAt(selectedSamplerPoint.expected_return)} r="11"
                                                    fill="none" stroke="rgba(255, 255, 255, 0.95)" stroke-width="2"
                                                    style="pointer-events: none;"/>
                                            <circle cx={samp.xAt(selectedSamplerPoint.volatility)}
                                                    cy={samp.yAt(selectedSamplerPoint.expected_return)} r="14"
                                                    fill="none" stroke="rgba(255, 255, 255, 0.30)" stroke-width="1"
                                                    style="pointer-events: none;"/>
                                        {/if}

                                        <!-- Current portfolio if available from EF result -->
                                        {#if efResult?.current_portfolio}
                                            <circle cx={samp.xAt(efResult.current_portfolio.volatility)}
                                                    cy={samp.yAt(efResult.current_portfolio.expected_return)} r="7"
                                                    fill="rgba(255, 0, 60, 0.95)" stroke="#fff" stroke-width="1.4">
                                                <title>Your portfolio · Sharpe {efResult.current_portfolio.sharpe.toFixed(2)}</title>
                                            </circle>
                                        {/if}

                                        <!-- Legend -->
                                        <g transform="translate({SAMP_W - SAMP_PAD.right - 220}, {SAMP_PAD.top + 6})">
                                            <circle cx="6" cy="6" r="3" fill={corrPointColor(0, 0.6)}/>
                                            <text x="16" y="9" fill="rgba(255,255,255,0.7)" font-size="10" class="mono">
                                                Sim · low correlation
                                            </text>
                                            <circle cx="6" cy="22" r="3" fill={corrPointColor(0.5, 0.6)}/>
                                            <text x="16" y="25" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Sim · medium
                                            </text>
                                            <circle cx="6" cy="38" r="3" fill={corrPointColor(1, 0.6)}/>
                                            <text x="16" y="41" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Sim · high correlation
                                            </text>
                                            <circle cx="6" cy="56" r="6" fill="rgba(255, 215, 0, 0.95)" stroke="#0a0a12"
                                                    stroke-width="1"/>
                                            <text x="16" y="60" fill="rgba(255,255,255,0.7)" font-size="10"
                                                  class="mono">Top-K
                                            </text>
                                            {#if efResult?.current_portfolio}
                                                <circle cx="6" cy="74" r="5" fill="rgba(255, 0, 60, 0.95)" stroke="#fff"
                                                        stroke-width="1.2"/>
                                                <text x="16" y="78" fill="rgba(255,255,255,0.7)" font-size="10"
                                                      class="mono">Your portfolio
                                                </text>
                                            {/if}
                                        </g>
                                    </svg>
                                </div>
                            {/if}

                            {#if selectedSamplerPoint}
                                <div class="selectionPanel">
                                    <div class="selectionHead">
                                        <div class="panelLabel">Selected portfolio composition</div>
                                        <button class="btn ghost xsmall" on:click={() => (selectedSamplerPoint = null)}>
                                            Clear
                                        </button>
                                    </div>
                                    <div class="selectionPills">
                                        {#each selectedSamplerPoint.tickers as t, k}
                                            <span class="samplerPill mono">
                                                {t}
                                                <span class="samplerPillWeight">{formatPct(selectedSamplerPoint.weights[k])}</span>
                                            </span>
                                        {/each}
                                    </div>
                                    <div class="selectionStats">
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Ann. return</div>
                                            <div class="mcStatValue mono {pnlClass(selectedSamplerPoint.expected_return)}">{formatPct(selectedSamplerPoint.expected_return)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Ann. volatility</div>
                                            <div class="mcStatValue mono">{formatPct(selectedSamplerPoint.volatility)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Sharpe</div>
                                            <div class="mcStatValue mono {sharpeClass(selectedSamplerPoint.sharpe)}">{selectedSamplerPoint.sharpe.toFixed(2)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Avg correlation</div>
                                            <div class="mcStatValue mono {selectedSamplerPoint.avg_correlation > 0.7 ? 'redText' : selectedSamplerPoint.avg_correlation < 0.3 ? 'greenText' : ''}">{selectedSamplerPoint.avg_correlation.toFixed(2)}</div>
                                        </div>
                                        <div class="mcStat">
                                            <div class="mcStatLabel">Composite score</div>
                                            <div class="mcStatValue mono bold">{selectedSamplerPoint.composite_score.toFixed(2)}</div>
                                        </div>
                                    </div>
                                </div>
                            {/if}

                            <div class="samplerToolbar">
                                <div class="rankSwitch">
                                    <button class="switchBtn" class:active={samplerRankBy === "composite"}
                                            on:click={() => (samplerRankBy = "composite")}>
                                        Rank by composite
                                    </button>
                                    <button class="switchBtn" class:active={samplerRankBy === "sharpe"}
                                            on:click={() => (samplerRankBy = "sharpe")}>
                                        Rank by Sharpe
                                    </button>
                                </div>
                                <div class="soft xsmall mono">
                                    {samplerResult.n_simulations_evaluated} unique portfolios evaluated
                                    · {samplerResult.n_simulations_failed} skipped · click any point for composition
                                </div>
                            </div>

                            <div class="tableWrap">
                                <table class="kittTable xsmallTable">
                                    <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>Tickers (weights)</th>
                                        <th>Ann. return</th>
                                        <th>Ann. vol</th>
                                        <th>Sharpe</th>
                                        <th>Avg ρ</th>
                                        <th>Composite</th>
                                    </tr>
                                    </thead>
                                    <tbody>
                                    {#each topList as p, i}
                                        <tr>
                                            <td><span class="mono bold">#{i + 1}</span></td>
                                            <td>
                                                {#each p.tickers as t, k}
                                                    <span class="samplerPill mono">
                                                        {t}
                                                        <span class="samplerPillWeight">{formatPct(p.weights[k])}</span>
                                                    </span>
                                                {/each}
                                            </td>
                                            <td><span
                                                    class="mono {pnlClass(p.expected_return)}">{formatPct(p.expected_return)}</span>
                                            </td>
                                            <td><span class="mono">{formatPct(p.volatility)}</span></td>
                                            <td><span class="mono {sharpeClass(p.sharpe)}">{p.sharpe.toFixed(2)}</span>
                                            </td>
                                            <td><span
                                                    class="mono {p.avg_correlation > 0.7 ? 'redText' : p.avg_correlation < 0.3 ? 'greenText' : ''}">{p.avg_correlation.toFixed(2)}</span>
                                            </td>
                                            <td><span class="mono bold">{p.composite_score.toFixed(2)}</span></td>
                                        </tr>
                                    {/each}
                                    </tbody>
                                </table>
                            </div>

                            <div class="mcFootnote soft">
                                {samplerResult.optimization === "max_sharpe" ? "Max-Sharpe (long-only Markowitz) weights" : "Equal-weight 1/N"}
                                · Rf = {formatPct(samplerResult.risk_free_rate)} · λ
                                = {samplerResult.diversification_weight} · {samplerResult.start_date_used}
                                → {samplerResult.end_date_used}
                                {#if Object.keys(samplerResult.errors).length > 0}
                                    · Skipped
                                    tickers: {Object.keys(samplerResult.errors).slice(0, 8).join(", ")}{Object.keys(samplerResult.errors).length > 8 ? "…" : ""}
                                {/if}
                            </div>
                        {:else if !isFetchingSampler}
                            <div class="emptyState">Click "Run sampler" to draw {samplerNSimulations}
                                random {samplerPortfolioSize}-asset portfolios from your referential and rank them by
                                composite score.
                            </div>
                        {/if}
                    </div>

                    <!-- MONTE CARLO SIMULATION -->
                    <div class="mcSection">
                        <div class="sectionTitle">Monte Carlo · Risk Simulation</div>
                        <div class="mcControls">
                            <label class="field inlineField">
                                <span class="label">Horizon (trading days)</span>
                                <input class="input mono xsmallInput" type="number" min="10" max="2520" step="1"
                                       bind:value={mcHorizonDays}/>
                            </label>
                            <label class="field inlineField">
                                <span class="label">Simulations</span>
                                <input class="input mono xsmallInput" type="number" min="50" max="20000" step="50"
                                       bind:value={mcNSimulations}/>
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
                            <button class="btn primary xsmall" on:click={runMonteCarlo}
                                    disabled={isFetchingMC || !positionView || positionView.rows.length === 0}>
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
                                    <svg viewBox="0 0 {MC_W} {MC_H}" class="mcChart"
                                         preserveAspectRatio="xMidYMid meet">
                                        <defs>
                                            <linearGradient id="mc-band-outer" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stop-color="rgba(0, 212, 255, 0.18)"/>
                                                <stop offset="100%" stop-color="rgba(0, 212, 255, 0.04)"/>
                                            </linearGradient>
                                            <linearGradient id="mc-band-inner" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stop-color="rgba(0, 212, 255, 0.35)"/>
                                                <stop offset="100%" stop-color="rgba(0, 212, 255, 0.12)"/>
                                            </linearGradient>
                                        </defs>

                                        <!-- Y gridlines + labels -->
                                        {#each mcData.yTicks as tick}
                                            <line x1={MC_PAD.left} y1={tick.y} x2={MC_W - MC_PAD.right} y2={tick.y}
                                                  stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
                                            <text x={MC_PAD.left - 8} y={tick.y + 3} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="end" class="mono">
                                                {tick.value.toFixed(0)}
                                            </text>
                                        {/each}

                                        <!-- Baseline (initial value) -->
                                        <line x1={MC_PAD.left} y1={mcData.baselineY} x2={MC_W - MC_PAD.right}
                                              y2={mcData.baselineY} stroke="rgba(255,255,255,0.35)" stroke-width="1"
                                              stroke-dasharray="3 3"/>

                                        <!-- 5-95 percentile band -->
                                        <path d={mcData.bandOuter} fill="url(#mc-band-outer)"/>
                                        <!-- 25-75 percentile band -->
                                        <path d={mcData.bandInner} fill="url(#mc-band-inner)"/>

                                        <!-- Spaghetti sample paths -->
                                        {#each mcData.samplePaths as p, i}
                                            <path d={p} fill="none" stroke="rgba(0, 212, 255, 0.18)"
                                                  stroke-width="0.7"/>
                                        {/each}

                                        <!-- Median -->
                                        <path d={mcData.median} fill="none" stroke="rgba(0, 212, 255, 0.95)"
                                              stroke-width="2"/>

                                        <!-- X-axis ticks -->
                                        {#each mcData.xTicks as tick}
                                            <line x1={tick.x} y1={MC_H - MC_PAD.bottom} x2={tick.x}
                                                  y2={MC_H - MC_PAD.bottom + 4} stroke="rgba(255,255,255,0.35)"/>
                                            <text x={tick.x} y={MC_H - MC_PAD.bottom + 16} fill="rgba(255,255,255,0.45)"
                                                  font-size="10" text-anchor="middle" class="mono">{tick.date}</text>
                                        {/each}

                                        <!-- Legend -->
                                        <g transform="translate({MC_W - MC_PAD.right - 130}, {MC_PAD.top + 4})">
                                            <rect x="0" y="0" width="14" height="8" fill="url(#mc-band-outer)"/>
                                            <text x="20" y="8" fill="rgba(255,255,255,0.65)" font-size="10"
                                                  class="mono">5–95%
                                            </text>
                                            <rect x="0" y="14" width="14" height="8" fill="url(#mc-band-inner)"/>
                                            <text x="20" y="22" fill="rgba(255,255,255,0.65)" font-size="10"
                                                  class="mono">25–75%
                                            </text>
                                            <line x1="0" y1="32" x2="14" y2="32" stroke="rgba(0, 212, 255, 0.95)"
                                                  stroke-width="2"/>
                                            <text x="20" y="36" fill="rgba(255,255,255,0.65)" font-size="10"
                                                  class="mono">Median
                                            </text>
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
                                    {mcResult.stats.n_simulations} simulations · {mcResult.stats.horizon_days} trading
                                    days · params estimated on {mcResult.stats.lookback_start}
                                    → {mcResult.stats.lookback_end}
                                    {#if Object.keys(mcResult.errors).length > 0}
                                        · Skipped tickers: {Object.keys(mcResult.errors).join(", ")}
                                    {/if}
                                </div>
                            {/if}
                        {:else if !isFetchingMC}
                            <div class="emptyState">Click "Run simulation" to project {mcHorizonDays} trading days
                                forward using {mcNSimulations} GBM paths.
                            </div>
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
                                            <span class="sidePill" class:buy={tx.side === "BUY"}
                                                  class:sell={tx.side === "SELL"}>
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
        background: radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
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
        box-shadow: 0 0 0 1px rgba(255, 0, 60, 0.08),
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
        background: linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
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

    .excludeHint {
        font-size: 11px;
        margin: 4px 0 12px 0;
    }

    .varLevelSwitch {
        display: flex;
        gap: 8px;
        align-items: center;
        margin: 8px 0 12px 0;
    }

    .chipBtn.activeLevel {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.35), rgba(255, 0, 60, 0.18));
        border-color: rgba(255, 0, 60, 0.55);
        color: rgba(255, 255, 255, 0.98);
    }

    .varLegendRow {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        align-items: center;
        margin: 0 0 10px 2px;
    }

    .varLegendItem {
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .varSwatch {
        width: 12px;
        height: 12px;
        border-radius: 3px;
        display: inline-block;
    }

    .varDash {
        width: 16px;
        border-top: 2px dashed rgba(255, 255, 255, 0.85);
        display: inline-block;
    }

    .varTableGap {
        margin-top: 14px;
    }

    .excludeChips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
    }

    .chipBtn {
        appearance: none;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.04);
        color: rgba(235, 235, 245, 0.9);
        border-radius: 999px;
        padding: 5px 12px;
        font-size: 11px;
        cursor: pointer;
        transition: background 140ms ease, color 140ms ease, border-color 140ms ease, opacity 140ms ease;
    }

    .chipBtn:hover {
        border-color: rgba(255, 0, 60, 0.5);
    }

    .chipBtn.excluded {
        background: rgba(255, 0, 60, 0.12);
        border-color: rgba(255, 0, 60, 0.55);
        color: rgba(255, 255, 255, 0.5);
        text-decoration: line-through;
        opacity: 0.8;
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

    /* --- PCA risk decomposition --- */

    .pcaVerdict {
        margin: 8px 0 16px 0;
        padding: 12px 14px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-left: 3px solid rgba(0, 212, 255, 0.7);
        background: rgba(0, 212, 255, 0.04);
        font-size: 12.5px;
        line-height: 1.55;
        color: rgba(235, 235, 245, 0.85);
    }

    .pcaVerdict.redText {
        border-left-color: rgba(255, 0, 60, 0.75);
        background: rgba(255, 0, 60, 0.05);
        color: rgba(235, 235, 245, 0.85);
    }

    .pcaVerdict.greenText {
        border-left-color: rgba(0, 220, 130, 0.7);
        background: rgba(0, 220, 130, 0.04);
        color: rgba(235, 235, 245, 0.85);
    }

    .pcaBlockTitle {
        margin-top: 24px;
    }

    .pcaChartHint {
        margin-top: 8px;
        line-height: 1.5;
        max-width: 900px;
    }

    .pcaBarGroup {
        cursor: pointer;
    }

    .pcaBarGroup:hover rect {
        filter: brightness(1.15);
    }

    .pcaBarGroup:focus {
        outline: none;
    }

    .pcaRow {
        cursor: pointer;
    }

    .pcaRow:hover {
        background: rgba(255, 255, 255, 0.03);
    }

    .pcaRowActive {
        background: rgba(0, 212, 255, 0.07);
    }

    .pcaInterp {
        font-size: 11px;
        color: rgba(235, 235, 245, 0.6);
        line-height: 1.45;
        display: inline-block;
        max-width: 420px;
    }

    .riskBarCell {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 130px;
    }

    .riskBarTrack {
        flex: 1;
        height: 6px;
        border-radius: 3px;
        background: rgba(255, 255, 255, 0.07);
        overflow: hidden;
        min-width: 50px;
    }

    .riskBarFill {
        height: 100%;
        border-radius: 3px;
        background: linear-gradient(90deg, rgba(0, 212, 255, 0.55), rgba(0, 212, 255, 0.95));
    }

    .pcaDetail {
        margin-top: 24px;
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
    }

    .pcaDetailMeta {
        margin-bottom: 12px;
    }

    .pcaLoadings {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 6px 24px;
    }

    .pcaLoadRow {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 11px;
    }

    .pcaLoadTicker {
        width: 78px;
        flex: none;
        color: rgba(235, 235, 245, 0.8);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .pcaLoadTrack {
        position: relative;
        flex: 1;
        height: 12px;
        min-width: 90px;
        background: rgba(255, 255, 255, 0.04);
        border-radius: 3px;
    }

    .pcaLoadCenter {
        position: absolute;
        left: 50%;
        top: 0;
        bottom: 0;
        width: 1px;
        background: rgba(255, 255, 255, 0.2);
    }

    .pcaLoadFill {
        position: absolute;
        top: 2px;
        bottom: 2px;
        border-radius: 2px;
    }

    .pcaLoadVal {
        width: 56px;
        flex: none;
        text-align: right;
        color: rgba(235, 235, 245, 0.75);
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

    .blViews {
        margin: 12px 0 4px 0;
        padding: 10px 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.02);
    }

    .blViewsHeader {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 8px;
    }

    .blViewRow {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        padding: 6px 0;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
    }

    .blViewRow:first-of-type {
        border-top: none;
    }

    .samplerToolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin: 14px 0 8px 0;
        flex-wrap: wrap;
    }

    .rankSwitch {
        display: inline-flex;
        gap: 0;
        border-radius: 10px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        overflow: hidden;
        background: rgba(0, 0, 0, 0.22);
    }

    .samplerPill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin: 2px 4px 2px 0;
        padding: 2px 8px;
        border-radius: 999px;
        background: rgba(0, 212, 255, 0.10);
        border: 1px solid rgba(0, 212, 255, 0.30);
        font-size: 11px;
        color: rgba(235, 245, 255, 0.92);
    }

    .samplerPillWeight {
        font-size: 10px;
        color: rgba(235, 245, 255, 0.6);
        background: rgba(0, 0, 0, 0.25);
        padding: 0 5px;
        border-radius: 6px;
    }

    .clickablePoint {
        cursor: pointer;
        transition: transform 100ms ease, filter 100ms ease;
    }

    .clickablePoint:hover {
        filter: brightness(1.35);
    }

    .selectionPanel {
        margin-top: 14px;
        padding: 14px 16px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.01));
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 12px;
    }

    .selectionHead {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }

    .selectionPills {
        display: flex;
        flex-wrap: wrap;
        gap: 2px;
        margin-bottom: 12px;
    }

    .selectionStats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
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
