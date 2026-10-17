<script>
    import {instance} from "$lib/axiosAPI.js";

    let isDownloading = false;
    let downloadError = "";
    let downloadOk = "";

    async function downloadPea() {
        if (isDownloading) return;
        downloadError = "";
        downloadOk = "";
        isDownloading = true;

        try {
            const res = await instance.get("/referential/pea/download", {
                responseType: "blob",
                timeout: 120000
            });

            const blob = new Blob([res.data], {type: "text/csv;charset=utf-8"});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "pea.csv";
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);

            downloadOk = "pea.csv downloaded.";
        } catch (/** @type {any} */ err) {
            downloadError =
                `Code: ${err?.response?.status ?? "?"}\n` +
                `Message: ${err?.message}`;
        } finally {
            isDownloading = false;
        }
    }

    let isChecking = false;
    let checkError = "";
    /** @type {{scraped_isins: number, known_isins: number, new_count: number, new_etfs: any[]} | null} */
    let checkResult = null;

    async function checkNewIsins() {
        if (isChecking) return;
        checkError = "";
        checkResult = null;
        isChecking = true;

        try {
            const res = await instance.get("/referential/pea/new-isins", {timeout: 120000});
            checkResult = res.data;
        } catch (/** @type {any} */ err) {
            checkError =
                `Code: ${err?.response?.status ?? "?"}\n` +
                `Message: ${err?.response?.data?.detail ?? err?.message}`;
        } finally {
            isChecking = false;
        }
    }
</script>

<div class="page">
    <div class="card">
        <div class="header">
            <h1 class="title">PEA ELIGIBLE ETFS</h1>
            <div class="subtitle">
                Source: Euronext — every ETF listed on Euronext flagged as PEA-eligible.
            </div>
        </div>

        <div class="body">
            <div class="actions">
                <button class="btn primary" type="button" on:click={downloadPea} disabled={isDownloading}>
                    {#if isDownloading}
                        Scraping Euronext…
                    {:else}
                        Download pea.csv
                    {/if}
                </button>

                <button class="btn" type="button" on:click={checkNewIsins} disabled={isChecking}>
                    {#if isChecking}
                        Checking new ISINs…
                    {:else}
                        Check new ISINs
                    {/if}
                </button>
            </div>

            {#if downloadError}
                <pre class="error">{downloadError}</pre>
            {/if}

            {#if downloadOk}
                <div class="ok">{downloadOk}</div>
            {/if}

            {#if checkError}
                <pre class="error">{checkError}</pre>
            {/if}

            {#if checkResult}
                <div class="summary">
                    <span><span class="mono">{checkResult.scraped_isins}</span> PEA ISINs on Euronext</span>
                    <span><span class="mono">{checkResult.known_isins}</span> ISINs in referential</span>
                    <span><span class="mono">{checkResult.new_count}</span> new</span>
                </div>

                <div class="tableWrap">
                    <table class="kittTable">
                        <thead>
                        <tr>
                            <th>ISIN</th>
                            <th>NAME</th>
                            <th>SYMBOL</th>
                            <th>MARKET</th>
                            <th>CURRENCY</th>
                            <th>LAST PRICE</th>
                            <th>LAST TRADE</th>
                        </tr>
                        </thead>
                        <tbody>
                        {#if checkResult.new_etfs.length === 0}
                            <tr>
                                <td class="empty" colspan="7">No new ISIN — the referential is up to date</td>
                            </tr>
                        {:else}
                            {#each checkResult.new_etfs as etf (etf.isin)}
                                <tr>
                                    <td><a class="mono" href={etf.url} target="_blank" rel="noopener noreferrer">{etf.isin}</a></td>
                                    <td>{etf.name}</td>
                                    <td>
                                        {#each etf.symbols as symbol}
                                            <span class="pill">{symbol}</span>
                                        {/each}
                                    </td>
                                    <td>{etf.markets.join(", ")}</td>
                                    <td><span class="mono">{etf.currency ?? "—"}</span></td>
                                    <td class="num">{etf.last_price ?? "—"}</td>
                                    <td>{etf.last_trade || "—"}</td>
                                </tr>
                            {/each}
                        {/if}
                        </tbody>
                    </table>
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    .page {
        min-height: calc(90vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        flex-direction: column;
        align-items: center;
        background: radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
        linear-gradient(180deg, #07080c, #04040a);
    }

    .card {
        width: min(1200px, 100%);
        border-radius: 16px;
        background: linear-gradient(180deg, rgba(10, 10, 18, 0.92), rgba(6, 6, 12, 0.92));
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow: 0 0 0 1px rgba(255, 0, 60, 0.08),
        0 20px 60px rgba(0, 0, 0, 0.65),
        0 0 30px rgba(255, 0, 60, 0.08);
        overflow: hidden;
        position: relative;
    }

    .header {
        position: relative;
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background: linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
        linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
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

    .body {
        padding: 24px 20px;
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }

    .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
    }

    .summary {
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
        font-size: 12px;
        color: rgba(235, 235, 245, 0.75);
    }

    .tableWrap {
        width: 100%;
        max-height: 60vh;
        overflow: auto;
    }

    .kittTable {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background: rgba(0, 0, 0, 0.25);
        border: 1px solid rgba(255, 0, 60, 0.18);
        border-radius: 14px;
    }

    .kittTable thead th {
        text-align: left;
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06)), #0a0a12;
        padding: 14px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .kittTable tbody td {
        padding: 12px 14px;
        font-size: 13px;
        color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.10);
    }

    .kittTable tbody tr:hover {
        background: rgba(255, 0, 60, 0.07);
    }

    .kittTable .num {
        text-align: right;
        font-variant-numeric: tabular-nums;
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        letter-spacing: 0.02em;
        color: rgba(255, 210, 220, 0.95);
    }

    a.mono {
        text-decoration: none;
    }

    a.mono:hover {
        text-decoration: underline;
    }

    .pill {
        display: inline-flex;
        margin: 2px 4px 2px 0;
        padding: 3px 9px;
        border-radius: 999px;
        font-size: 11px;
        letter-spacing: 0.06em;
        color: rgba(255, 255, 255, 0.85);
        background: rgba(255, 0, 60, 0.10);
        border: 1px solid rgba(255, 0, 60, 0.22);
    }

    .empty {
        text-align: center;
        color: rgba(235, 235, 245, 0.55) !important;
    }

    .error {
        margin: 0;
        font-size: 12px;
        color: rgba(255, 120, 140, 0.95);
        white-space: pre-wrap;
    }

    .ok {
        font-size: 12px;
        color: rgba(120, 255, 180, 0.9);
    }

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
        letter-spacing: 0.04em;
        cursor: pointer;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10), 0 0 14px rgba(255, 0, 60, 0.10);
        transition: transform 140ms ease, border 140ms ease, box-shadow 140ms ease;
    }

    .btn:hover:not(:disabled) {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
    }

    .btn:disabled {
        opacity: 0.6;
        cursor: wait;
    }

    .btn.primary {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.40), rgba(255, 0, 60, 0.22));
        border-color: rgba(255, 0, 60, 0.65);
        color: rgba(255, 255, 255, 0.98);
        box-shadow:
                inset 0 0 14px rgba(255, 0, 60, 0.26),
                0 0 22px rgba(255, 0, 60, 0.30);
        font-weight: 600;
    }
</style>
