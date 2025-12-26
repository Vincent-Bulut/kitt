<script>
    import {instance} from "$lib/axiosAPI.js";

    export let data;

    // Assets fetched by load()
    let assets = data?.props?.assets ?? [];

    // Search
    let query = "";

    // Live filtered assets
    $: q = query.trim().toLowerCase();
    $: filteredAssets =
        q === ""
            ? assets
            : assets.filter((a) => {
                const isin = (a?.isin ?? "").toString().toLowerCase();
                const name = (a?.name ?? "").toString().toLowerCase();
                const currency = (a?.currency ?? "").toString().toLowerCase();
                const symbol = (a?.symbol ?? "").toString().toLowerCase();
                return (
                    isin.includes(q) ||
                    name.includes(q) ||
                    currency.includes(q) ||
                    symbol.includes(q)
                );
            });

    // ---- Upload state ----
    let isDragging = false;
    let isUploading = false;
    let uploadError = "";
    let uploadOk = "";
    let inputEl;

    function isExcel(file) {
        const name = (file?.name ?? "").toLowerCase();
        return name.endsWith(".xlsx") || name.endsWith(".xls");
    }

    async function uploadFile(file) {
        uploadError = "";
        uploadOk = "";

        if (!file) {
            uploadError = "No file detected.";
            return;
        }

        const name = (file.name ?? "").toLowerCase();
        if (!name.endsWith(".xlsx") && !name.endsWith(".xls")) {
            uploadError = "Only .xlsx / .xls files are allowed.";
            return;
        }

        isUploading = true;

        try {
            const fd = new FormData();
            fd.append("file", file, file.name);

            // IMPORTANT : axios DOIT envoyer fd tel quel
            const res = await instance.request({
                url: "/referential/upload-excel",
                method: "POST",
                data: fd,

                transformRequest: [(data) => data], // empêche JSON.stringify
                headers: {
                    // NE PAS METTRE Content-Type
                    // axios + browser ajouteront multipart/form-data; boundary=...
                },
                timeout: 120000
            });

            uploadOk = `Upload OK — inserted/updated: ${
                res?.data?.inserted_or_updated ?? "?"
            }, rows_in_file: ${res?.data?.rows_in_file ?? "?"}`;
        } catch (err) {
            uploadError =
                `Code: ${err?.response?.status}\n` +
                `Data: ${JSON.stringify(err?.response?.data)}\n` +
                `Message: ${err?.message}`;
        } finally {
            isUploading = false;
            isDragging = false;
        }
    }


    function onDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        isDragging = false;

        const file = e.dataTransfer?.files?.[0];
        console.log("Dropped file:", file);
        uploadFile(file);
    }

    function onDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        isDragging = true;
    }

    function onDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        isDragging = false;
    }

    function onBrowseClick() {
        if (isUploading) return;
        inputEl?.click();
    }

    function onFilePicked(e) {
        const file = e.currentTarget?.files?.[0];
        uploadFile(file);
        // allow selecting same file twice
        e.currentTarget.value = "";
    }

    function onDropzoneKeydown(e) {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onBrowseClick();
        }
    }
</script>

<div class="page">
    <div class="card">
        <div class="header">
            <div class="headerGrid">
                <!-- LEFT -->
                <div class="headerLeft">
                    <h1 class="title">ASSET TERMINAL</h1>
                    <div class="subtitle">{filteredAssets.length} asset(s) shown</div>

                    <div class="searchWrap">
                        <input
                                type="text"
                                class="searchInput"
                                placeholder="Search ISIN, name, symbol, currency…"
                                bind:value={query}
                        />
                    </div>
                </div>

                <!-- RIGHT -->
                <div class="headerRight">
                    <div
                            class="dropzone {isDragging ? 'dragging' : ''} {isUploading ? 'uploading' : ''}"
                            role="button"
                            tabindex="0"
                            aria-label="Upload Excel file"
                            on:click={onBrowseClick}
                            on:keydown={onDropzoneKeydown}
                            on:dragover={onDragOver}
                            on:dragleave={onDragLeave}
                            on:drop={onDrop}
                    >
                        <div class="dzTitle">
                            {#if isUploading}
                                Uploading…
                            {:else}
                                Drag & drop an .xlsx/.xls file here (or click to browse)
                            {/if}
                        </div>

                        {#if uploadError}
                            <pre class="dzError">{uploadError}</pre>
                        {/if}

                        {#if uploadOk}
                            <div class="dzOk">{uploadOk}</div>
                        {/if}

                        <input
                                bind:this={inputEl}
                                class="hiddenInput"
                                type="file"
                                accept=".xlsx,.xls"
                                on:change={onFilePicked}
                        />
                    </div>
                </div>
            </div>

            <div class="scanline" aria-hidden="true"></div>
        </div>

        <!-- TABLE -->
        <div class="tableWrap">
            <table class="kittTable">
                <thead>
                <tr>
                    <th>ISIN</th>
                    <th>NAME</th>
                    <th>CURRENCY</th>
                    <th>SYMBOL</th>
                </tr>
                </thead>

                <tbody>
                {#if filteredAssets.length === 0}
                    <tr>
                        <td class="empty" colspan="4">No assets found</td>
                    </tr>
                {:else}
                    {#each filteredAssets as asset}
                        <tr>
                            <td><span class="mono">{asset.isin}</span></td>
                            <td>{asset.name}</td>
                            <td><span class="mono">{asset.currency}</span></td>
                            <td><span class="pill">{asset.symbol}</span></td>
                        </tr>
                    {/each}
                {/if}
                </tbody>
            </table>
        </div>
    </div>
</div>

<style>
    /* Page */
    .page {
        min-height: calc(100vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        justify-content: center;
        background: radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
        linear-gradient(180deg, #07080c, #04040a);
    }

    /* Card */
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

    /* Header */
    .header {
        position: relative;
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background: linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
        linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }

    .headerGrid {
        display: grid;
        grid-template-columns: 1fr 420px; /* dropzone column on right */
        gap: 16px;
        align-items: start;
    }

    .headerLeft {
        min-width: 0;
    }

    .headerRight {
        display: flex;
        justify-content: flex-end;
    }

    @media (max-width: 900px) {
        .headerGrid {
            grid-template-columns: 1fr;
        }

        .headerRight {
            justify-content: flex-start;
        }
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

    /* Search */
    .searchWrap {
        margin-top: 12px;
        max-width: 360px;
    }

    .searchInput {
        width: 100%;
        padding: 10px 14px;
        border-radius: 10px;
        font-size: 13px;
        color: rgba(255, 255, 255, 0.9);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.10), rgba(255, 0, 60, 0.02));
        border: 1px solid rgba(255, 0, 60, 0.28);
        outline: none;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.12),
        0 0 14px rgba(255, 0, 60, 0.08);
        transition: border 150ms ease, box-shadow 150ms ease;
    }

    .searchInput::placeholder {
        color: rgba(235, 235, 245, 0.45);
        letter-spacing: 0.04em;
    }

    .searchInput:focus {
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.18),
        0 0 20px rgba(255, 0, 60, 0.25);
    }

    /* Dropzone */
    .dropzone {
        width: 100%;
        border-radius: 12px;
        border: 1px dashed rgba(255, 0, 60, 0.35);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.06), rgba(0, 0, 0, 0.10));
        padding: 12px 14px;
        cursor: pointer;
        user-select: none;
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.10),
        0 0 18px rgba(255, 0, 60, 0.06);
        transition: transform 120ms ease, border 120ms ease, box-shadow 120ms ease;
    }

    .dropzone:hover {
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 16px rgba(255, 0, 60, 0.16),
        0 0 22px rgba(255, 0, 60, 0.10);
    }

    .dropzone.dragging {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.85);
        box-shadow: inset 0 0 18px rgba(255, 0, 60, 0.22),
        0 0 26px rgba(255, 0, 60, 0.18);
    }

    .dropzone.uploading {
        opacity: 0.85;
        cursor: progress;
    }

    .dzTitle {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.88);
    }

    .dzHint {
        margin-top: 4px;
        font-size: 12px;
        color: rgba(235, 235, 245, 0.55);
    }

    .dzError {
        margin-top: 8px;
        font-size: 12px;
        color: rgba(255, 160, 160, 0.95);
        white-space: pre-wrap;
    }

    .dzOk {
        margin-top: 8px;
        font-size: 12px;
        color: rgba(180, 255, 200, 0.95);
    }

    .hiddenInput {
        display: none;
    }

    /* Scanline */
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
            transform: translateY(260px);
        }
    }

    /* Table */
    .tableWrap {
        padding: 14px;
        max-height: 65vh;
        overflow-y: auto;
        overflow-x: auto;
    }

    .kittTable {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background: rgba(0, 0, 0, 0.25);
        border: 1px solid rgba(255, 0, 60, 0.18);
        border-radius: 14px;
        overflow: hidden;
    }

    .kittTable thead th {
        text-align: left;
        font-size: 12px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
        padding: 14px 14px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .kittTable tbody td {
        padding: 12px 14px;
        font-size: 14px;
        color: rgba(235, 235, 245, 0.85);
        border-bottom: 1px solid rgba(255, 0, 60, 0.10);
    }

    .kittTable tbody tr {
        transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
    }

    .kittTable tbody tr:hover {
        background: rgba(255, 0, 60, 0.07);
        box-shadow: inset 0 0 0 1px rgba(255, 0, 60, 0.20);
    }

    .kittTable tbody tr:hover td {
        color: rgba(255, 255, 255, 0.92);
    }

    .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        letter-spacing: 0.02em;
        color: rgba(255, 210, 220, 0.95);
        text-shadow: 0 0 10px rgba(255, 0, 60, 0.18);
    }

    .pill {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.85);
        background: rgba(255, 0, 60, 0.10);
        border: 1px solid rgba(255, 0, 60, 0.22);
        box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .empty {
        text-align: center;
        padding: 22px 14px !important;
        color: rgba(235, 235, 245, 0.55) !important;
    }

    .kittTable thead th:first-child {
        border-top-left-radius: 14px;
    }

    .kittTable thead th:last-child {
        border-top-right-radius: 14px;
    }

    .tableWrap::-webkit-scrollbar {
        height: 10px;
        width: 10px;
    }

    .tableWrap::-webkit-scrollbar-thumb {
        background: rgba(255, 0, 60, 0.25);
        border-radius: 999px;
        border: 2px solid rgba(0, 0, 0, 0.35);
    }

    .tableWrap::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.25);
    }
</style>
