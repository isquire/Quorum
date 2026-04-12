// Small glue — dismissible alerts auto-hide, confirm dialogs, etc.
(function () {
    'use strict';
    // Auto-dismiss flash alerts after 5s.
    document.addEventListener('DOMContentLoaded', function () {
        var alerts = document.querySelectorAll('.alert.alert-dismissible');
        alerts.forEach(function (el) {
            setTimeout(function () {
                if (window.bootstrap) {
                    var a = new bootstrap.Alert(el);
                    a.close();
                }
            }, 5000);
        });
    });
})();
