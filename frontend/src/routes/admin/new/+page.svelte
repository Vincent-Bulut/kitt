<script>
  import { instance } from "$lib/axiosAPI.js";

  let isSubmitting = false;
  let error = "";

  let form = {
    name: "",
    start_date: "",
    end_date: "2100-12-31",
    manager_name: "",
    description: ""
  };

  async function submit() {
    error = "";

    if (!form.name.trim()) return (error = "Name is required.");
    if (!form.start_date) return (error = "Start date is required.");
    if (form.end_date && form.end_date < form.start_date) {
      return (error = "End date must be >= start date.");
    }

    isSubmitting = true;

    try {
      const payload = {
        name: form.name.trim(),
        start_date: form.start_date,
        end_date: form.end_date ? form.end_date : null,
        manager_name: form.manager_name.trim() ? form.manager_name.trim() : null,
        description: form.description.trim() ? form.description.trim() : null
      };

      const response = await instance.post("/admin/portfolio", payload);
      const created = response.data;

      // Redirect back to list (or to the created portfolio page)
      window.location.href = `/admin`; // ou `/portfolios/${created?.id}`
    } catch (err) {
      error =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        "Unable to create portfolio.";
    } finally {
      isSubmitting = false;
    }
  }
</script>

<div class="page">
  <div class="card">
    <div class="header">
      <h1 class="title">CREATE PORTFOLIO</h1>
      <div class="subtitle">Define name, dates, manager and optional description</div>
      <div class="scanline" aria-hidden="true"></div>
    </div>

    <div class="body">
      <div class="formGrid">
        <label class="field full">
          <span class="label">Name *</span>
          <input
            class="input"
            type="text"
            bind:value={form.name}
            placeholder="e.g. Amundi STOXX Europe 600 Banks UCITS ETF Acc"
          />
        </label>

        <label class="field">
          <span class="label">Start date *</span>
          <input class="input mono" type="date" bind:value={form.start_date} />
        </label>

        <label class="field">
          <span class="label">End date</span>
          <input class="input mono" type="date" bind:value={form.end_date} />
        </label>

        <label class="field full">
          <span class="label">Manager</span>
          <input class="input" type="text" bind:value={form.manager_name} placeholder="e.g. Vincent" />
        </label>

        <label class="field full">
          <span class="label">Description</span>
          <textarea class="textarea" rows="5" bind:value={form.description} placeholder="Optional notes…" />
        </label>
      </div>

      {#if error}
        <div class="errorBox">{error}</div>
      {/if}

      <div class="actions">
        <a class="btn ghost" href="/admin">Cancel</a>
        <button class="btn" type="button" on:click={submit} disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create"}
        </button>
      </div>
    </div>
  </div>
</div>

<style>
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

  .card {
    width: min(900px, 100%);
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

  .body { padding: 16px; }

  .formGrid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 720px) {
    .formGrid { grid-template-columns: 1fr; }
  }

  .field { display: flex; flex-direction: column; gap: 6px; }
  .field.full { grid-column: 1 / -1; }

  .label {
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(235, 235, 245, 0.58);
  }

  .input, .textarea {
    border-radius: 12px;
    border: 1px solid rgba(255, 0, 60, 0.22);
    background: rgba(255, 0, 60, 0.06);
    color: rgba(255, 255, 255, 0.9);
    padding: 10px 12px;
    outline: none;
    box-shadow: inset 0 0 12px rgba(255, 0, 60, 0.10);
    transition: border 150ms ease, box-shadow 150ms ease;
  }
  .input:focus, .textarea:focus {
    border-color: rgba(255, 0, 60, 0.55);
    box-shadow: inset 0 0 14px rgba(255, 0, 60, 0.16), 0 0 18px rgba(255, 0, 60, 0.18);
  }

  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  }

  .errorBox {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 0, 60, 0.30);
    background: rgba(255, 0, 60, 0.10);
    color: rgba(255, 230, 235, 0.95);
    font-size: 13px;
    line-height: 1.35;
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
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 0, 60, 0.28);
    background: rgba(255, 0, 60, 0.10);
    color: rgba(255, 255, 255, 0.9);
    text-decoration: none;
    font-size: 13px;
    letter-spacing: 0.04em;
    cursor: pointer;
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
</style>
