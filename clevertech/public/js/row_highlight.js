// ============================================================
// GLOBAL ROW HIGHLIGHT BASED ON ROUTE (works in all versions)
// ============================================================

function is_report_route(route) {
    // route = ["query-report", "Report Name"] OR ["Report", "Report Name"]
    return (
        route[0] === "query-report" ||
        route[0] === "Report"
    );
}

function wait_for_datatable(callback) {
    const check = setInterval(() => {
        const dt = document.querySelector(".dt-instance, .datatable");
        if (dt) {
            clearInterval(check);
            callback(dt);
        }
    }, 200);
}

// Attach highlight logic to a datatable root element
function attach_highlight(dt_root) {
    const root = dt_root;

    // avoid duplicate binding
    if (root.__highlight_attached) return;
    root.__highlight_attached = true;

    root.addEventListener("click", function(e) {
        const cell = e.target.closest(".dt-cell");
        if (!cell) return;

        const row = cell.closest(".dt-row");
        if (!row) return;

        // Remove old highlights
        root.querySelectorAll(".dt-row--highlight")
            .forEach(r => r.classList.remove("dt-row--highlight"));

        // Apply highlight
        row.classList.add("dt-row--highlight");
    });
}


// GLOBAL ROUTER HOOK
frappe.router.on("change", () => {
    const route = frappe.get_route();

    if (!is_report_route(route)) return;

    // after navigating to a report, wait until datatable loads
    wait_for_datatable((dt_root) => {
        attach_highlight(dt_root);
    });
});


// GLOBAL STYLE
frappe.dom.set_style(`
    .dt-row--highlight {
        background-color: #EDC0E8 !important;
        transition: background-color 0.15s ease;
    }
    .dt-cell--focus {
        box-shadow: none !important;
        border: none !important;
    }
`);

