(function () {
  let apiBaseUrl = "";

  function safeString(value, maxLength = 500) {
    if (value === undefined || value === null) {
      return "";
    }
    return String(value).slice(0, maxLength);
  }

  function write(event, details = {}) {
    if (!apiBaseUrl) {
      return;
    }

    const payload = {
      service: "frontend",
      event: safeString(event, 80),
      page: `${window.location.pathname}${window.location.search}`,
      origin: window.location.origin,
      apiBaseUrl,
      online: navigator.onLine,
      userAgent: navigator.userAgent,
      ...details
    };

    fetch(`${apiBaseUrl}/client-log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(() => {
      // If the API itself is unreachable, the backend cannot receive client diagnostics.
    });
  }

  window.YT_CLIENT_LOG = {
    init(url) {
      apiBaseUrl = safeString(url, 300).replace(/\/$/, "");
      write("client_loaded", { language: navigator.language });
    },
    write
  };

  window.addEventListener("error", (event) => {
    write("window_error", {
      errorMessage: event.message,
      source: safeString(event.filename, 300),
      line: event.lineno,
      column: event.colno
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason || {};
    write("unhandled_rejection", {
      errorName: safeString(reason.name, 120),
      errorMessage: safeString(reason.message || reason, 500)
    });
  });
})();
