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
            <button class="btn primary" type="button" on:click={downloadPea} disabled={isDownloading}>
                {#if isDownloading}
                    Scraping Euronext…
                {:else}
                    Download pea.csv
                {/if}
            </button>

            {#if downloadError}
                <pre class="error">{downloadError}</pre>
            {/if}

            {#if downloadOk}
                <div class="ok">{downloadOk}</div>
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
