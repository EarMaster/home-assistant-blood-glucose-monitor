var body = document.querySelector('body')
var menuTrigger = document.querySelector('#toggle-main-menu-mobile');
var menuContainer = document.querySelector('#main-menu-mobile');

menuTrigger.onclick = function() {
    menuContainer.classList.toggle('open');
    menuTrigger.classList.toggle('is-active')
    body.classList.toggle('lock-scroll')
}

// Language switcher: remember the choice (the start page then no longer
// follows the browser language) and keep the query, e.g. the builder's
// prefilled entities.
document.querySelectorAll('.language-switch a').forEach(function (link) {
    link.addEventListener('click', function () {
        try { localStorage.setItem('bgm-language', link.dataset.language); } catch (error) {}
        link.href = link.href.split('?')[0].split('#')[0] + location.search + location.hash;
    });
});
