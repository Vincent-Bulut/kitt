<script lang="ts">
    import { instance } from "$lib/axiosAPI.js";
    import { onMount } from "svelte";

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

    let view: "log" | "positions" = "positions";

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
        } catch (err: any) {
            errorMessage = err?.response?.data?.detail || err?.message || "Unable to load portfolio data.";
        } finally {
            isLoadingData = false;
        }
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
        if (form.transaction_fee.trim()) {
            const fee = parseFloat(form.transaction_fee);
            if (Number.isFinite(fee)) payload.transaction_fee = fee;
        }
        if (form.amount.trim()) {
            const amt = parseFloat(form.amount);
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

    onMount(async () => {
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
                    <h1 class="title">TRANSACTIONS COCKPIT</h1>
                    <div class="subtitle">
                        Log new trades, browse history and inspect derived positions per portfolio.
                    </div>
                </div>
                <div class="statusWrap">
                    <span class="status">WAC</span>
                    <span class="status soft">Yahoo prices</span>
                </div>
            </div>
            <div class="chipRow">
                <span class="chip">Buy / Sell</span>
                <span class="chip">Auto P&amp;L</span>
                <span class="chip">Weights</span>
                <span class="chip">TER</span>
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
                    <button class="switchBtn" class:active={view === "log"} on:click={() => (view = "log")}>
                        Transactions log
                    </button>
                </div>

                <button class="btn ghost" type="button" on:click={loadData} disabled={isLoadingData || selectedPortfolioId === null}>
                    {isLoadingData ? "Refreshing…" : "Refresh"}
                </button>
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
                        <input class="input mono" type="number" step="any" min="0" bind:value={form.transaction_fee} placeholder="0" />
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

    .topBar {
        display: flex;
        gap: 12px;
        align-items: flex-end;
        flex-wrap: wrap;
    }
    .topBar .field { min-width: 240px; flex: 1 1 240px; }

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
        padding: 10px 16px;
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
        transition: background 140ms ease, color 140ms ease;
    }
    .switchBtn:hover { color: rgba(255, 255, 255, 0.95); background: rgba(255, 0, 60, 0.06); }
    .switchBtn.active {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.35), rgba(255, 0, 60, 0.18));
        color: rgba(255, 255, 255, 0.98);
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.22);
    }

    .formCard {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 12px 16px;
    }
    .formCard summary {
        list-style: none;
        cursor: pointer;
        padding: 4px 0;
        display: flex;
        align-items: center;
    }
    .formCard summary::-webkit-details-marker { display: none; }
    .formCard summary::before {
        content: "▸";
        margin-right: 10px;
        transition: transform 140ms ease;
        color: rgba(255, 0, 60, 0.85);
    }
    .formCard[open] summary::before { transform: rotate(90deg); }

    .panelLabel {
        font-size: 12px; letter-spacing: 0.16em; text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95); text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
    }
    .moduleHint { font-size: 11px; color: rgba(235, 235, 245, 0.48); font-family: ui-monospace, monospace; }

    .modulePanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 16px;
    }
    .moduleHead {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 10px;
        margin-bottom: 12px;
    }

    .formGrid {
        margin-top: 12px;
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
    }
    @media (max-width: 1100px) { .formGrid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 600px) { .formGrid { grid-template-columns: 1fr; } }

    .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
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

    .actions { margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px; }

    .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 10px 14px;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.28);
        background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 255, 255, 0.90);
        font-size: 13px;
        cursor: pointer;
        transition: transform 140ms ease, border 140ms ease;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(255, 0, 60, 0.55); }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .btn.ghost {
        background: rgba(255, 255, 255, 0.02);
        border-color: rgba(255, 255, 255, 0.10);
        color: rgba(235, 235, 245, 0.75);
    }
    .btn.ghost:hover { border-color: rgba(255, 255, 255, 0.25); }
    .btn.primary {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.40), rgba(255, 0, 60, 0.22));
        border-color: rgba(255, 0, 60, 0.65);
        color: rgba(255, 255, 255, 0.98);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.26), 0 0 22px rgba(255, 0, 60, 0.30);
        font-weight: 600;
    }
    .btn.xsmall { padding: 6px 10px; font-size: 11px; }

    .errorBox, .okBox {
        margin-top: 12px; padding: 10px 12px; border-radius: 12px;
        font-size: 13px; line-height: 1.4;
    }
    .errorBox {
        border: 1px solid rgba(255, 0, 60, 0.30); background: rgba(255, 0, 60, 0.10);
        color: rgba(255, 230, 235, 0.95);
    }
    .okBox {
        border: 1px solid rgba(34, 197, 94, 0.30); background: rgba(34, 197, 94, 0.10);
        color: rgba(200, 255, 220, 0.95);
    }

    .kpiRow {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 14px;
    }
    @media (max-width: 1100px) { .kpiRow { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 600px) { .kpiRow { grid-template-columns: 1fr; } }

    .kpiCard {
        border: 1px solid rgba(255, 0, 60, 0.14);
        background: rgba(255, 0, 60, 0.04);
        border-radius: 12px;
        padding: 10px 12px;
        min-width: 0;
    }
    .kpiK {
        font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
        color: rgba(235, 235, 245, 0.55);
        margin-bottom: 4px;
    }
    .kpiV { font-size: 15px; color: rgba(255, 255, 255, 0.92); }

    .tableWrap {
        overflow: auto;
        border-radius: 12px;
        border: 1px solid rgba(255, 0, 60, 0.12);
        max-height: 65vh;
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
    .nameCell {
        max-width: 240px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .greenText { color: rgba(34, 197, 94, 0.96); }
    .redText { color: rgba(255, 80, 100, 0.96); }
    .soft { color: rgba(235, 235, 245, 0.55); }

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
</style>
