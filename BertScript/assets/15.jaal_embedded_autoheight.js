/* Original Jaal embedded frame: size the parent iframe to actual Dash content.
 * The two apps share an origin and port. Standalone Jaal and Stage 4's main
 * Dash page are intentionally unaffected; graph data/zoom are never changed.
 */
(function () {
    "use strict";

    if (window.parent === window ||
            window.location.pathname.indexOf("/jaal-original/") !== 0) {
        return;
    }

    function start() {
        var frame;
        try {
            frame = window.frameElement;
        } catch (_error) {
            return;
        }
        if (!frame || !frame.classList ||
                !frame.classList.contains("jaal-original-iframe")) {
            return;
        }

        var pending = false;
        var lastHeight = 0;
        var currentRoot = null;

        function measure() {
            pending = false;
            if (!currentRoot || !currentRoot.isConnected) {
                return;
            }
            var bounds = currentRoot.getBoundingClientRect();
            // Ignore the iframe's viewport/body height: it can be 800px even
            // when the actual Jaal graph + settings occupy much less space.
            var naturalBottom = bounds.bottom + window.scrollY + 16;
            if (!Number.isFinite(naturalBottom) || naturalBottom < 100) {
                return;
            }
            // Bounds prevent unstable pages or a broken third-party layout
            // from creating arbitrarily giant iframes. Longer settings remain
            // scrollable inside the iframe if they exceed this maximum.
            var nextHeight = Math.max(640, Math.min(1600, Math.ceil(naturalBottom)));
            if (Math.abs(nextHeight - lastHeight) >= 4) {
                frame.style.height = nextHeight + "px";
                lastHeight = nextHeight;
            }
        }

        function schedule() {
            if (pending) {
                return;
            }
            pending = true;
            window.requestAnimationFrame(measure);
        }

        function attach() {
            var root = document.getElementById("jaal-original-content");
            if (!root) {
                return false;
            }
            currentRoot = root;
            if (window.ResizeObserver) {
                var resizer = new ResizeObserver(schedule);
                resizer.observe(root);
            }
            window.addEventListener("resize", schedule);
            window.addEventListener("load", schedule, {once: true});
            schedule();
            return true;
        }

        if (!attach() && window.MutationObserver) {
            // Dash hydrates its layout after the asset scripts are loaded.
            // Watch only until the real Jaal content appears, not forever.
            var watcher = new MutationObserver(function () {
                if (attach()) {
                    watcher.disconnect();
                }
            });
            watcher.observe(document.documentElement, {
                childList: true,
                subtree: true
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, {once: true});
    } else {
        start();
    }
})();
