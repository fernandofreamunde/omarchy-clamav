import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Owns the ClamAV status JSON and drives ctl.py for scan / update / poll.
Item {
  id: root

  property var settings: ({})
  property var status: Model.emptyStatus()
  property bool busy: false
  property string lastError: ""

  readonly property string pluginDir: {
    var dir = String(Qt.resolvedUrl("."))
    if (dir.indexOf("file://") === 0) dir = dir.substring(7)
    return dir.replace(/\/$/, "")
  }
  readonly property string ctlPath: pluginDir + "/ctl.py"
  readonly property string homeDir: Quickshell.env("HOME") || ""
  readonly property string downloadsDir: {
    var xdg = Quickshell.env("XDG_DOWNLOAD_DIR")
    if (xdg && xdg !== "") return xdg
    return homeDir + "/Downloads"
  }
  readonly property int pollMs: {
    if (scanning || updating || installing) return 400
    return intSetting("pollIntervalSec", 30, 5, 300) * 1000
  }
  readonly property string defaultTarget: String(setting("defaultTarget", "downloads"))
  readonly property bool scanning: !!(status && status.scan && status.scan.running) || status.phase === "scanning"
  readonly property bool updating: !!(status && status.database && status.database.updating) || status.phase === "updating"
  readonly property bool installing: !!(status && status.install && status.install.installing) || status.phase === "installing"
  readonly property bool needsSetup: Model.needsSetup(status)
  readonly property bool reminderDue: !!(status && status.database && status.database.reminderDue)
  readonly property bool alarming: needsSetup || reminderDue || status.phase === "infected" || status.phase === "error"

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function intSetting(name, fallback, min, max) {
    var n = parseInt(String(setting(name, fallback)), 10)
    if (!isFinite(n)) n = fallback
    return Math.max(min, Math.min(max, n))
  }

  function apply(raw) {
    var parsed = Model.parseStatus(raw)
    status = parsed
    if (parsed && parsed.lastError)
      lastError = String(parsed.lastError)
    else if (ctlProcess.running === false)
      lastError = lastError
  }

  function refresh(notifyReminder) {
    if (ctlProcess.running) return
    busy = true
    var command = ["python3", ctlPath, "status"]
    if (notifyReminder === true) command.push("--notify")
    ctlProcess.command = command
    ctlProcess.running = true
  }

  function startScan(targetKey) {
    if (ctlProcess.running) return
    var key = String(targetKey || defaultTarget || "downloads")
    var target = Model.expandScanTarget(key, homeDir, downloadsDir)
    var label = key === "home" ? "Home" : (key === "downloads" ? "Downloads" : key)
    busy = true
    lastError = ""
    ctlProcess.command = ["python3", ctlPath, "scan", target, "--label", label]
    ctlProcess.running = true
  }

  function stop() {
    if (ctlProcess.running) return
    busy = true
    ctlProcess.command = ["python3", ctlPath, "stop"]
    ctlProcess.running = true
  }

  function updateDatabase() {
    if (ctlProcess.running) return
    busy = true
    lastError = ""
    ctlProcess.command = ["python3", ctlPath, "update"]
    ctlProcess.running = true
  }

  function installOrConfigure() {
    if (ctlProcess.running) return
    busy = true
    lastError = ""
    ctlProcess.command = ["python3", ctlPath, "install"]
    ctlProcess.running = true
  }

  function ackReminder() {
    if (ctlProcess.running) return
    ctlProcess.command = ["python3", ctlPath, "ack-reminder"]
    ctlProcess.running = true
  }

  Process {
    id: ctlProcess
    running: false
    onExited: function(exitCode) {
      root.busy = false
      if (exitCode !== 0 && root.lastError === "")
        root.lastError = "ClamAV control failed"
      // After starting scan/update, immediately re-poll so the bar flips to live state.
      Qt.callLater(function() { pollTimer.restart() })
    }

    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.apply(text)
    }

    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") root.lastError = text.trim()
    }
  }

  FileView {
    id: statusFile
    path: {
      var state = Quickshell.env("XDG_STATE_HOME")
      var home = Quickshell.env("HOME") || ""
      var rootDir = (state && state !== "") ? state : (home + "/.local/state")
      return rootDir + "/omarchy/clamav/status.json"
    }
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.apply(text())
  }

  Timer {
    id: pollTimer
    interval: root.pollMs
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh(true)
  }
}
