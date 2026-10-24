// Apply the saved theme before first paint to avoid a flash (absent = follow the system).
try {
  var t = localStorage.getItem("ayd.theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
