.pragma library

function emptyStatus() {
  return {
    version: 1,
    phase: "idle",
    updatedAt: "",
    scan: {
      running: false,
      target: "",
      label: "",
      filesTotal: 0,
      filesDone: 0,
      infected: 0,
      errors: 0,
      percent: 0,
      currentFile: "",
      startedAt: "",
      finishedAt: "",
      infectedFiles: [],
      summary: "",
      exitCode: null
    },
    database: {
      path: "/var/lib/clamav",
      ageHours: null,
      ageDays: null,
      lastUpdatedAt: "",
      stale: false,
      reminderDue: false,
      updating: false,
      lastUpdateOk: null,
      lastUpdateAt: "",
      lastUpdateMessage: "",
      remindedAt: ""
    },
    daemon: {
      active: false,
      freshclamActive: false,
      enabled: false,
      freshclamEnabled: false
    },
    install: {
      packageInstalled: false,
      binariesPresent: false,
      databasePresent: false,
      ready: false,
      needsInstall: true,
      needsConfigure: false,
      installing: false,
      lastInstallOk: null,
      lastInstallAt: "",
      lastInstallMessage: ""
    },
    lastError: ""
  }
}

function parseStatus(raw) {
  try {
    var parsed = JSON.parse(String(raw || ""))
    if (!parsed || typeof parsed !== "object") return emptyStatus()
    return parsed
  } catch (e) {
    return emptyStatus()
  }
}

function numberValue(value) {
  var n = Number(value)
  return isFinite(n) ? n : 0
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function installReady(status) {
  return !!(status && status.install && status.install.ready)
}

function needsSetup(status) {
  if (!status || !status.install) return true
  return !status.install.ready
}

function setupButtonLabel(status) {
  if (status && status.install && status.install.installing) return "Installing…"
  if (status && status.install && status.install.needsConfigure) return "Configure ClamAV"
  return "Install & configure"
}

function setupHint(status) {
  if (status && status.install && status.install.installing)
    return "Installing the package, downloading definitions, and enabling services. Approve the polkit prompt if asked."
  if (status && status.install && status.install.needsConfigure)
    return "ClamAV is installed but not fully set up. This enables the scanner daemon, starts the definition updater, and downloads the virus database."
  return "ClamAV is not installed. This installs the Arch package, downloads virus definitions, and enables clamav-daemon + clamav-freshclam."
}

function phaseLabel(status) {
  var phase = String(status && status.phase || "idle")
  if (phase === "installing" || (status && status.install && status.install.installing))
    return "Installing ClamAV"
  if (phase === "setup" || needsSetup(status)) {
    if (status && status.install && status.install.needsConfigure) return "Needs configuration"
    return "Not installed"
  }
  if (phase === "scanning") return "Scanning"
  if (phase === "updating") return "Updating definitions"
  if (phase === "infected") return "Threats found"
  if (phase === "error") return "Error"
  if (status && status.database && status.database.reminderDue) return "Update definitions"
  if (status && status.database && status.database.stale) return "Definitions getting old"
  return "Ready"
}

function compactLabel(status) {
  if (!status) return ""
  if (status.phase === "scanning" || (status.scan && status.scan.running)) {
    var pct = Math.round(numberValue(status.scan && status.scan.percent))
    return pct > 0 ? (pct + "%") : "…"
  }
  if (status.phase === "installing" || (status.install && status.install.installing))
    return "…"
  if (status.phase === "updating" || (status.database && status.database.updating))
    return "upd"
  if (status.phase === "infected")
    return String(Math.round(numberValue(status.scan && status.scan.infected)))
  if (needsSetup(status))
    return "setup"
  if (status.database && status.database.reminderDue)
    return "!"
  return ""
}

function ageText(status) {
  var days = status && status.database ? status.database.ageDays : null
  if (days === null || days === undefined || days === "") return "unknown age"
  var n = numberValue(days)
  if (n < 1) {
    var hours = numberValue(status.database.ageHours)
    if (hours < 1) return "updated just now"
    return "updated " + Math.round(hours) + "h ago"
  }
  if (n < 1.5) return "updated 1 day ago"
  return "updated " + Math.round(n) + " days ago"
}

function scanProgressText(status) {
  var scan = status && status.scan ? status.scan : {}
  if (!scan.running && status && status.phase !== "scanning") {
    if (scan.summary) return scan.summary
    return "No scan running"
  }
  var done = Math.round(numberValue(scan.filesDone))
  var total = Math.round(numberValue(scan.filesTotal))
  var pct = Math.round(numberValue(scan.percent))
  if (total > 0)
    return done + " / " + total + " files · " + pct + "%"
  if (done > 0)
    return done + " files · " + pct + "%"
  return "Starting…"
}

function expandScanTarget(key, home, downloads) {
  if (key === "home") return home || "~"
  if (key === "downloads") return downloads || ((home || "~") + "/Downloads")
  return downloads || ((home || "~") + "/Downloads")
}
