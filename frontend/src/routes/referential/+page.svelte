<script>
  export let data;

  // This variable already contains your fetched assets
  let assets = data?.props?.assets ?? [];

  // Search query
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
</script>

<div class="page">
  <div class="card">
    <div class="header">
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

      <div class="scanline" aria-hidden="true"></div>
    </div>

    <div class="tableWrap">
      <table class="kittTable">
        <thead>
          <tr>
            <th>ISIN</th>
            <th>Name</th>
            <th>Currency</th>
            <th>Symbol</th>
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
  /* Page flexbox centered */
  .page {
    min-height: calc(100vh - 80px);
    padding: 96px 20px 40px;
    padding-top: 12vh;
    display: flex;
    align-items: center;
    justify-content: center;

    background:
      radial-gradient(1200px 600px at 50% 20%, rgba(255, 0, 60, 0.12), transparent 60%),
      linear-gradient(180deg, #07080c, #04040a);
  }

  /* KITT card */
  .card {
    width: min(1100px, 100%);
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

  .header {
    position: relative;
    padding: 18px 20px 16px;
    border-bottom: 1px solid rgba(255, 0, 60, 0.16);
    background:
      linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
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

  /* Search bar */
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

    background:
      linear-gradient(180deg, rgba(255, 0, 60, 0.10), rgba(255, 0, 60, 0.02));
    border: 1px solid rgba(255, 0, 60, 0.28);

    outline: none;
    box-shadow:
      inset 0 0 12px rgba(255, 0, 60, 0.12),
      0 0 14px rgba(255, 0, 60, 0.08);

    transition: border 150ms ease, box-shadow 150ms ease;
  }

  .searchInput::placeholder {
    color: rgba(235, 235, 245, 0.45);
    letter-spacing: 0.04em;
  }

  .searchInput:focus {
    border-color: rgba(255, 0, 60, 0.55);
    box-shadow:
      inset 0 0 14px rgba(255, 0, 60, 0.18),
      0 0 20px rgba(255, 0, 60, 0.25);
  }

  /* subtle moving scanline */
  .scanline {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(
      180deg,
      transparent,
      rgba(255, 0, 60, 0.08),
      transparent
    );
    height: 120px;
    transform: translateY(-120px);
    animation: scan 4.5s linear infinite;
    opacity: 0.75;
  }

  @keyframes scan {
    0% { transform: translateY(-120px); }
    100% { transform: translateY(260px); }
  }

  /* Table wrapper for nice border + scroll on small screens */
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
    background:
      linear-gradient(180deg, rgba(255, 0, 60, 0.18), rgba(255, 0, 60, 0.06));
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

  /* nicer rounded corners for thead */
  .kittTable thead th:first-child { border-top-left-radius: 14px; }
  .kittTable thead th:last-child  { border-top-right-radius: 14px; }

  /* Optional: thin red scrollbar */
  .tableWrap::-webkit-scrollbar { height: 10px; width: 10px; }
  .tableWrap::-webkit-scrollbar-thumb {
    background: rgba(255, 0, 60, 0.25);
    border-radius: 999px;
    border: 2px solid rgba(0, 0, 0, 0.35);
  }
  .tableWrap::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.25); }
</style>
