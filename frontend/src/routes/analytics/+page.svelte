<script lang="ts">
    const modules = [
        {
            title: "Performance",
            description: "Compare 1D to 5Y performance for one or more tickers.",
            href: "/analytics/perf",
            tag: "YAHOO"
        },
        {
            title: "Arithmetic Return",
            description: "Compute return between two dates with nearest-trading-day handling.",
            href: "/analytics/arithmetic-return",
            tag: "YAHOO"
        },
        {
            title: "Cumulative Returns",
            description: "Track cumulative return series over time across multiple tickers.",
            href: "/analytics/cumulative-return",
            tag: "YAHOO"
        },
        {
            title: "Drawdowns",
            description: "Inspect drawdown depth, duration, and recovery path.",
            href: "/analytics/drawdowns",
            tag: "YAHOO"
        },
        {
            title: "Annualized Volatility",
            description: "Measure period and annualized volatility by frequency and return mode.",
            href: "/analytics/annualized-volatility",
            tag: "YAHOO"
        },
        {
            title: "VaR / ES",
            description: "Estimate historical, Gaussian, and Cornish-Fisher risk metrics.",
            href: "/analytics/var-es",
            tag: "YAHOO"
        }
    ];

    const chips = [
        "Multi-ticker",
        "KITT UI",
    ];
</script>

<div class="page">
    <section class="card">
        <div class="scanline" aria-hidden="true"></div>

        <header class="header">
            <div class="headerTop">
                <div>
                    <h1 class="title">ANALYTICS TERMINAL</h1>
                    <div class="subtitle">
                        Launch market analytics modules from a single cockpit.
                    </div>
                </div>

                <div class="statusWrap">
                    <span class="status">LIVE</span>
                    <span class="status soft">Yahoo</span>
                </div>
            </div>

            <div class="chipRow">
                {#each chips as chip}
                    <span class="chip">{chip}</span>
                {/each}
            </div>
        </header>

        <div class="body">
            <div class="heroPanel">
                <div class="heroLabel">LANDING ZONE</div>
                <p class="heroText">
                    Choose an analytics module, submit your tickers and dates, then inspect results.
                </p>

                <div class="heroActions">
                    <a class="btn" href="/analytics/perf">Open Performance</a>
                    <a class="btn ghost" href="/analytics/var-es">Open VaR / ES</a>
                </div>
            </div>

            <div class="grid">
                {#each modules as mod}
                    <a class="moduleCard" href={mod.href}>
                        <div class="moduleTop">
                            <span class="moduleTag">{mod.tag}</span>
                            <span class="moduleArrow">↗</span>
                        </div>

                        <div class="moduleTitle">{mod.title}</div>
                        <div class="moduleDesc">{mod.description}</div>
                    </a>
                {/each}
            </div>
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
    }

    .card {
        width: min(1200px, 100%);
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
        0% { transform: translateY(-120px); }
        100% { transform: translateY(320px); }
    }

    .header {
        position: relative;
        padding: 18px 20px 16px;
        border-bottom: 1px solid rgba(255, 0, 60, 0.16);
        background:
                linear-gradient(90deg, rgba(255, 0, 60, 0.10), transparent 60%),
                linear-gradient(180deg, rgba(255, 0, 60, 0.06), transparent 70%);
    }

    .headerTop {
        display: flex;
        align-items: flex-start;
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
        justify-content: flex-end;
    }

    .status,
    .chip,
    .moduleTag {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid rgba(255, 0, 60, 0.22);
        background: rgba(255, 0, 60, 0.10);
        box-shadow: 0 0 18px rgba(255, 0, 60, 0.08);
    }

    .status {
        padding: 6px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.88);
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

    .chip {
        padding: 5px 10px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(235, 235, 245, 0.72);
        background: rgba(255, 0, 60, 0.07);
    }

    .body {
        padding: 16px;
        display: grid;
        gap: 16px;
    }

    .heroPanel {
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.22);
        padding: 16px;
    }

    .heroLabel {
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: rgba(255, 0, 60, 0.95);
        text-shadow: 0 0 12px rgba(255, 0, 60, 0.25);
    }

    .heroText {
        margin: 10px 0 0;
        max-width: 760px;
        color: rgba(235, 235, 245, 0.78);
        line-height: 1.6;
        font-size: 14px;
    }

    .heroActions {
        margin-top: 14px;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
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
        text-decoration: none;
        font-size: 13px;
        letter-spacing: 0.04em;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10), 0 0 16px rgba(255, 0, 60, 0.10);
        transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease;
    }

    .btn:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 0, 60, 0.55);
        box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 20px rgba(255, 0, 60, 0.22);
    }

    .btn.ghost {
        background: rgba(255, 0, 60, 0.06);
        border-color: rgba(255, 0, 60, 0.18);
        color: rgba(255, 255, 255, 0.82);
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 14px;
    }

    @media (max-width: 1000px) {
        .grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 640px) {
        .grid {
            grid-template-columns: 1fr;
        }
    }

    .moduleCard {
        display: block;
        text-decoration: none;
        border-radius: 14px;
        border: 1px solid rgba(255, 0, 60, 0.18);
        background: rgba(0, 0, 0, 0.24);
        padding: 16px;
        transition: transform 140ms ease, box-shadow 140ms ease, border 140ms ease, background 140ms ease;
        box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.04);
    }

    .moduleCard:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 0, 60, 0.42);
        background: rgba(255, 0, 60, 0.07);
        box-shadow:
                inset 0 0 14px rgba(255, 0, 60, 0.10),
                0 0 22px rgba(255, 0, 60, 0.10);
    }

    .moduleTop {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
    }

    .moduleTag {
        padding: 4px 9px;
        font-size: 10px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(255, 255, 255, 0.82);
    }

    .moduleArrow {
        color: rgba(255, 210, 220, 0.88);
        font-size: 18px;
    }

    .moduleTitle {
        margin-top: 12px;
        color: rgba(255, 255, 255, 0.94);
        font-size: 14px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .moduleDesc {
        margin-top: 8px;
        color: rgba(235, 235, 245, 0.60);
        font-size: 13px;
        line-height: 1.5;
    }
</style>