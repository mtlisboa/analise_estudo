(function () {
    var hub = document.getElementById('room-hub');
    if (!hub) return;
    var links = hub.querySelectorAll('a');
    function selectSection(hash) {
        var target = document.getElementById(hash.slice(1));
        if (target && target.tagName === 'DETAILS') target.open = true;
        links.forEach(function (link) {
            if (link.getAttribute('href') === hash) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
        });
    }
    links.forEach(function (link) {
        link.addEventListener('click', function () { selectSection(link.getAttribute('href')); });
    });
    window.addEventListener('hashchange', function () { selectSection(location.hash || '#room-overview'); });
    selectSection(location.hash || '#room-overview');
}());
