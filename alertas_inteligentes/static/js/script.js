(function () {
    function iniciarDrawerSidebar() {
        const shell = document.querySelector("#ia-shell");
        const toggle = document.querySelector("#iaSidebarToggle");

        console.log("Drawer sidebar carregado:", { shell, toggle });

        if (!shell || !toggle) {
            console.warn("Drawer não iniciado: #ia-shell ou #iaSidebarToggle não encontrado.");
            return;
        }

        const estadoSalvo = localStorage.getItem("synchro_ai_sidebar");

        if (estadoSalvo === "collapsed") {
            shell.classList.add("sidebar-collapsed");
            toggle.textContent = "›";
        } else {
            shell.classList.remove("sidebar-collapsed");
            toggle.textContent = "‹";
        }

        toggle.onclick = function (event) {
            event.preventDefault();
            event.stopPropagation();

            console.log("Clique no drawer detectado");

            shell.classList.toggle("sidebar-collapsed");

            const fechado = shell.classList.contains("sidebar-collapsed");

            localStorage.setItem(
                "synchro_ai_sidebar",
                fechado ? "collapsed" : "expanded"
            );

            toggle.textContent = fechado ? "›" : "‹";
        };
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciarDrawerSidebar);
    } else {
        iniciarDrawerSidebar();
    }
})();