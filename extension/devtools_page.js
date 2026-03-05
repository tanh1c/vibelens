// This script creates the DevTools panel.
chrome.devtools.panels.create(
    "VibeLens",
    "icons/icon16.png",
    "devtools.html",
    function (panel) {
        console.log("VibeLens panel created");
    }
);
