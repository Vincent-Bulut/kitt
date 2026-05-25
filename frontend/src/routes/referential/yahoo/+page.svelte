<script>
    import {instance} from "$lib/axiosAPI.js";
    import {goto} from "$app/navigation";

    export let data;

    // Assets fetched by load()
    let assets = data?.props?.assets ?? [];

    // Search
    let query = "";

    // Selection — keyed by asset.symbol (the ticker analytics expects)
    let selected = new Set();

    function toggleOne(symbol) {
        if (!symbol) return;
        if (selected.has(symbol)) selected.delete(symbol);
        else selected.add(symbol);
        selected = selected; // trigger reactivity
    }

    function clearSelection() {
        selected = new Set();
    }

    $: filteredSymbols = filteredAssets
        .map((a) => a?.symbol)
        .filter(Boolean);

    $: visibleSelectedCount = filteredSymbols.filter((s) => selected.has(s)).length;
    $: allVisibleSelected =
        filteredSymbols.length > 0 &&
        visibleSelectedCount === filteredSymbols.length;
    $: someVisibleSelected =
        visibleSelectedCount > 0 && visibleSelectedCount < filteredSymbols.length;

    function toggleAllVisible() {
        if (allVisibleSelected) {
            for (const s of filteredSymbols) selected.delete(s);
        } else {
            for (const s of filteredSymbols) selected.add(s);
        }
        selected = selected;
    }

    function openAnalytics() {
        if (selected.size === 0) return;
        const tickers = Array.from(selected).join(",");
        goto(`/analytics/all?tickers=${encodeURIComponent(tickers)}`);
    }

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
                    <th class="checkCol">
                        <input
                                type="checkbox"
                                class="rowCheckbox"
                                aria-label="Select all visible"
                                checked={allVisibleSelected}
                                indeterminate={someVisibleSelected}
                                on:change={toggleAllVisible}
                                disabled={filteredSymbols.length === 0}
                        />
                    </th>
                    <th>ISIN</th>
                    <th>NAME</th>
                    <th>CURRENCY</th>
                    <th>SYMBOL</th>
                </tr>
                </thead>

                <tbody>
                {#if filteredAssets.length === 0}
                    <tr>
                        <td class="empty" colspan="5">No assets found</td>
                    </tr>
                {:else}
                    {#each filteredAssets as asset}
                        <tr class:rowSelected={asset.symbol && selected.has(asset.symbol)}>
                            <td class="checkCol">
                                <input
                                        type="checkbox"
                                        class="rowCheckbox"
                                        aria-label={`Select ${asset.symbol ?? asset.isin}`}
                                        checked={asset.symbol ? selected.has(asset.symbol) : false}
                                        disabled={!asset.symbol}
                                        on:change={() => toggleOne(asset.symbol)}
                                />
                            </td>
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

    {#if selected.size > 0}
        <div class="selectionBar" role="region" aria-label="Selection actions">
            <div class="selectionInfo">
                <span class="selectionCount mono">{selected.size}</span>
                <span class="selectionLabel">selected</span>
                <span class="selectionPreview mono">{Array.from(selected).slice(0, 4).join(", ")}{selected.size > 4 ? `, +${selected.size - 4}` : ""}</span>
            </div>
            <div class="selectionActions">
                <button class="btn ghost" type="button" on:click={clearSelection}>Clear</button>
                <button class="btn primary" type="button" on:click={openAnalytics}>
                    View analytics →
                </button>
            </div>
        </div>
    {/if}
</div>

<style>
    /* Page */
    .page {
        min-height: calc(90vh - 80px);
        padding: 12vh 20px 40px;
        display: flex;
        flex-direction: column;
        align-items: center;
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
        max-height: 60vh;
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

    /* Checkbox column */
    .checkCol {
        width: 44px;
        text-align: center !important;
        padding-left: 14px !important;
        padding-right: 8px !important;
    }

    .rowCheckbox {
        appearance: none;
        -webkit-appearance: none;
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid rgba(255, 0, 60, 0.45);
        background: rgba(255, 0, 60, 0.06);
        box-shadow: inset 0 0 8px rgba(255, 0, 60, 0.12);
        cursor: pointer;
        position: relative;
        transition: border 120ms ease, background 120ms ease, box-shadow 120ms ease;
    }

    .rowCheckbox:hover:not(:disabled) {
        border-color: rgba(255, 0, 60, 0.85);
        box-shadow: inset 0 0 10px rgba(255, 0, 60, 0.18), 0 0 8px rgba(255, 0, 60, 0.18);
    }

    .rowCheckbox:checked {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.55), rgba(255, 0, 60, 0.30));
        border-color: rgba(255, 0, 60, 0.85);
        box-shadow: inset 0 0 8px rgba(255, 0, 60, 0.30), 0 0 10px rgba(255, 0, 60, 0.25);
    }

    .rowCheckbox:checked::after {
        content: "";
        position: absolute;
        top: 2px;
        left: 5px;
        width: 5px;
        height: 9px;
        border-right: 2px solid #fff;
        border-bottom: 2px solid #fff;
        transform: rotate(45deg);
    }

    .rowCheckbox:indeterminate {
        background: linear-gradient(180deg, rgba(255, 0, 60, 0.40), rgba(255, 0, 60, 0.20));
        border-color: rgba(255, 0, 60, 0.85);
    }

    .rowCheckbox:indeterminate::after {
        content: "";
        position: absolute;
        top: 7px;
        left: 3px;
        right: 3px;
        height: 2px;
        background: #fff;
        border-radius: 1px;
    }

    .rowCheckbox:disabled {
        opacity: 0.35;
        cursor: not-allowed;
    }

    .kittTable tbody tr.rowSelected {
        background: rgba(255, 0, 60, 0.10);
        box-shadow: inset 0 0 0 1px rgba(255, 0, 60, 0.28);
    }

    .kittTable tbody tr.rowSelected td {
        color: rgba(255, 255, 255, 0.95);
    }

    /* Floating selection bar */
    .selectionBar {
        position: sticky;
        bottom: 16px;
        margin-top: 14px;
        align-self: center;
        display: flex;
        gap: 14px;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        padding: 12px 16px;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.40);
        background: linear-gradient(180deg, rgba(20, 10, 18, 0.96), rgba(10, 6, 12, 0.96));
        box-shadow:
                0 0 0 1px rgba(255, 0, 60, 0.10),
                0 12px 36px rgba(0, 0, 0, 0.6),
                0 0 26px rgba(255, 0, 60, 0.22);
        backdrop-filter: blur(8px);
        z-index: 10;
        width: min(1200px, 100%);
    }

    .selectionInfo {
        display: flex;
        align-items: baseline;
        gap: 10px;
        flex-wrap: wrap;
        min-width: 0;
    }

    .selectionCount {
        font-size: 18px;
        color: rgba(255, 0, 60, 0.98);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.40);
        letter-spacing: 0.04em;
    }

    .selectionLabel {
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.70);
    }

    .selectionPreview {
        font-size: 12px;
        color: rgba(235, 235, 245, 0.55);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 360px;
    }

    .selectionActions {
        display: flex;
        gap: 10px;
        flex-shrink: 0;
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

    .btn:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
    }

    .btn.ghost {
        background: rgba(255, 255, 255, 0.02);
        border-color: rgba(255, 255, 255, 0.10);
        color: rgba(235, 235, 245, 0.75);
        box-shadow: none;
    }

    .btn.ghost:hover {
        border-color: rgba(255, 255, 255, 0.25);
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

    .btn.primary:hover {
        border-color: rgba(255, 0, 60, 0.85);
        box-shadow:
                inset 0 0 18px rgba(255, 0, 60, 0.34),
                0 0 28px rgba(255, 0, 60, 0.42);
    }
</style>
