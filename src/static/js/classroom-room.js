(function () {
    var hub = document.getElementById('room-hub');
    if (!hub) return;
    var links = Array.from(hub.querySelectorAll('a'));
    var panels = Array.from(document.querySelectorAll('[data-room-panel]'));
    hub.setAttribute('role', 'tablist');
    links.forEach(function (link, index) {
        link.setAttribute('role', 'tab');
        link.id = 'room-tab-' + index;
        link.setAttribute('aria-controls', link.hash.slice(1));
        var panel = document.getElementById(link.hash.slice(1));
        panel.setAttribute('role', 'tabpanel');
        panel.tabIndex = 0;
        panel.setAttribute('aria-labelledby', link.id);
    });
    function selectSection(hash) {
        if (hash === '#room-hub' || hash === '#room-overview' || hash === '#room-activities') hash = '#room-content';
        var selected = links.find(function (link) { return link.hash === hash; }) || links[0];
        panels.forEach(function (panel) { panel.hidden = '#' + panel.id !== selected.hash; });
        links.forEach(function (link) {
            var active = link === selected;
            link.setAttribute('aria-selected', String(active));
            link.tabIndex = active ? 0 : -1;
            if (active) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
        });
        var target = document.getElementById(selected.hash.slice(1));
        if (target.tagName === 'DETAILS') target.open = true;
    }
    links.forEach(function (link, index) {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            history.replaceState(null, '', link.hash);
            selectSection(link.hash);
        });
        link.addEventListener('keydown', function (event) {
            var next;
            if (event.key === 'ArrowRight') next = (index + 1) % links.length;
            if (event.key === 'ArrowLeft') next = (index + links.length - 1) % links.length;
            if (event.key === 'Home') next = 0;
            if (event.key === 'End') next = links.length - 1;
            if (next === undefined) return;
            event.preventDefault(); links[next].focus(); links[next].click();
        });
    });
    document.querySelectorAll('a[href="#room-notices"]').forEach(function (link) {
        link.addEventListener('click', function () { selectSection('#room-notices'); });
    });
    window.addEventListener('hashchange', function () { selectSection(location.hash); });
    var invalidNotice = document.querySelector('#room-notices .errorlist');
    selectSection(invalidNotice ? '#room-notices' : location.hash);
}());
