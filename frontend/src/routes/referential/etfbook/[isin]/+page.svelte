
<script>
  import { page } from "$app/state";
  $: exchangeBloombergCode = decodeURIComponent(page.params.isin);
</script>

<main>
  <h1>Hello {exchangeBloombergCode}</h1>
</main>

<style>
  main {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh; /* Occupe toute la hauteur de la fenêtre */
    margin: 0;
  }
</style>
