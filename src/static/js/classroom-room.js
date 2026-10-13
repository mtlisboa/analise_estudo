(function () {
    var hub = document.getElementById('room-hub');
    if (!hub) return;
    function openHub() { if (location.hash === '#room-hub') hub.open = true; }
    openHub();
    window.addEventListener('hashchange', openHub);
    document.querySelectorAll('a[href="#room-hub"]').forEach(function (link) {
        link.addEventListener('click', function () { hub.open = true; });
    });
}());
