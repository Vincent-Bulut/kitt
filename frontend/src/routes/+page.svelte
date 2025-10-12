<script>
    // Aucun script nécessaire pour un effet purement visuel
</script>

<div class="kitt-container">
    <!-- Le rayon rouge -->
    <div class="kitt-light"></div>
</div>

<style>
    /* Conteneur principal */
    .kitt-container {
        width: 100%;
        height: 100vh;
        background: black; /* Fond noir pour l'effet immersif */
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
        position: relative;
    }

    /* Le rayon rouge animé */
    .kitt-light {
        width: 60%;
        height: 10px;
        background: linear-gradient(90deg,
            rgba(0, 0, 0, 0) 0%,
            rgba(255, 0, 0, 1) 50%,
            rgba(0, 0, 0, 0) 100%);
        border-radius: 5px;
        animation: kittAnim 2s infinite ease-in-out;
        position: relative;
        box-shadow: 0px 0px 20px 10px rgba(255, 0, 0, 0.5); /* Effet lumineux */
    }

    /* Animation du rayon rouge */
    @keyframes kittAnim {
        0%, 100% {
            transform: translateX(-100%);
        }
        50% {
            transform: translateX(100%);
        }
    }
</style>