// Applies the saved theme before the first paint. This file is served from the site origin as a
// classic blocking script, so it runs under the page CSP (script-src 'self') without an inline
// script, and it must stay in sync with src/lib/theme.ts (storage key, class and attribute names).
;(function () {
  var theme = 'dark'
  try {
    var saved = window.localStorage.getItem('academy-theme')
    if (saved === 'light' || saved === 'dark') theme = saved
  } catch {
    // Storage can be blocked (private mode, disabled cookies): keep the default theme.
  }
  var root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  root.setAttribute('data-theme', theme)
})()
