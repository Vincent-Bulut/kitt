<script></script>

<nav class="header-kitt">
    <a href="/" class="logo">K</a>
    <div class="tabs">
        <div class="tab dropdown">
            <span class="dropdown-trigger">Portfolio</span>
            <div class="dropdown-menu">
                <a href="/positions" class="dropdown-item">Positions</a>
                <a href="/risk" class="dropdown-item">Risk</a>
            </div>
        </div>
        <a href="/referential" class="tab">Referential</a>
    </div>
    <a href="/admin" class="admin-tab">Admin</a>
</nav>

<style>
    .header-kitt {
        background: linear-gradient(90deg, #0d0d0d, #1a1a1a);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
        padding: 15px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px solid #333;
        position: fixed;
        top: 0;
        width: 100%;
        z-index: 1000;
    }

    .logo {
        font-size: 3rem;
        font-weight: 900;
        color: #ff3333;
        text-shadow: 0 0 8px #ff3333, 0 0 12px #ff5555, 0 0 20px rgba(255, 85, 85, 0.9);
        text-decoration: none;
        text-transform: uppercase;
        margin-right: 30px;
        padding: 5px 10px;
        transition: all 0.3s ease;
    }

    .logo:hover {
        text-shadow: 0 0 12px #ff6666, 0 0 18px rgba(255, 60, 60, 1);
        transform: scale(1.2);
    }

    .tabs {
        display: flex;
        gap: 30px;
        flex-grow: 1;
    }

    .tab {
        position: relative;
        color: #ddd;
        font-size: 1.3rem;
        font-weight: bold;
        text-transform: uppercase;
        text-decoration: none;
        padding: 10px 15px;
        border: 2px solid transparent;
        border-radius: 4px;
        white-space: nowrap;
        transition: all 0.3s ease;
    }

    .tab:hover {
        border-color: #ff3333;
        color: #fff;
        transform: scale(1.08);
        box-shadow: 0 0 10px rgba(255, 50, 50, 0.8);
    }

    .admin-tab {
        color: #ddd;
        font-size: 1.3rem;
        font-weight: bold;
        text-transform: uppercase;
        text-decoration: none;
        padding: 10px 15px;
        border-radius: 4px;
        border: 2px solid transparent;
        white-space: nowrap;
        margin-left: auto;
        transition: all 0.3s ease;
        margin-right: 50px;
    }

    .admin-tab:hover {
        border-color: #ff3333;
        color: #fff;
        transform: scale(1.08);
        box-shadow: 0 0 10px rgba(255, 50, 50, 0.8);
    }

    .dropdown {
        position: relative;
    }

    .dropdown-menu {
        display: none;
        position: absolute;
        top: 110%;
        left: 0;
        background: #121212;
        border-radius: 8px;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
        padding: 10px 0;
        z-index: 1000;
        flex-direction: column;
        opacity: 0;
        transform: translateY(-10px);
        transition: all 0.3s ease;
    }

    .dropdown:hover .dropdown-menu {
        display: flex;
        opacity: 1;
        transform: translateY(0);
    }

    .dropdown-item {
        color: #ddd;
        font-size: 1.2rem;
        text-transform: uppercase;
        text-decoration: none;
        padding: 10px 20px;
        margin: 5px 10px;
        border-radius: 4px;
        border: 2px solid transparent;
        transition: all 0.3s ease;
    }

    .dropdown-item:hover {
        background: #1e1e1e;
        border-color: #ff3333;
        color: #fff;
        box-shadow: 0 0 10px rgba(255, 50, 50, 0.7);
    }

    @media screen and (max-width: 768px) {
        .header-kitt {
            flex-direction: column;
            align-items: flex-start;
            padding: 10px;
        }

        .tabs {
            gap: 15px;
            flex-wrap: wrap;
        }

        .logo {
            margin-right: 15px;
        }

        .admin-tab {
            margin-left: 0;
        }
    }
</style>