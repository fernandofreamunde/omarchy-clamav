import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "glink.clamav"
  ipcTarget: "glink.clamav"
  manageIpc: false

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color track: Style.selectedFillFor(foreground, Color.accent)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var status: svc.status || Model.emptyStatus()
  readonly property string label: Model.compactLabel(status)
  readonly property bool scanning: svc.scanning
  readonly property bool updating: svc.updating
  readonly property bool alarming: svc.alarming
  readonly property int glyphBox: Math.max(Style.bar.iconCanvas, Style.bar.iconFont + Style.space(2))
  readonly property real progress: {
    if (updating) return -1
    return Model.clamp(Model.numberValue(status.scan && status.scan.percent) / 100, 0, 1)
  }

  function refresh() { svc.refresh(false) }
  function scanDownloads() { svc.startScan("downloads") }
  function scanHome() { svc.startScan("home") }
  function stopWork() { svc.stop() }
  function updateDb() { svc.updateDatabase() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    svc.refresh(false)
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  Service {
    id: svc
    settings: root.settings
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.refresh(); return "ok" }
    function scan(): string { root.scanDownloads(); return "ok" }
    function update(): string { root.updateDb(); return "ok" }
    function status(): string {
      return Model.phaseLabel(root.status) + " · " + Model.ageText(root.status)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    labelVisible: false
    hasVisualContent: true
    tooltipText: {
      if (root.scanning)
        return "ClamAV scanning · " + Model.scanProgressText(root.status)
      if (root.updating)
        return "ClamAV updating virus definitions"
      if (root.status.phase === "infected")
        return "ClamAV found threats · click for details"
      if (root.alarming)
        return "ClamAV definitions need updating · click to refresh"
      return "ClamAV · click to scan or update"
    }
    horizontalMargin: 5
    fixedWidth: root.vertical ? -1 : Math.ceil(chip.implicitWidth + button.scaledHorizontalMargin * 2)
    fixedHeight: root.vertical ? Math.ceil(chip.implicitHeight + Style.space(8)) : -1
    active: root.alarming || root.scanning || root.updating

    onPressed: function(pressedButton) {
      if (pressedButton === Qt.MiddleButton) root.refresh()
      else if (pressedButton === Qt.RightButton) {
        if (root.scanning || root.updating) root.stopWork()
        else root.scanDownloads()
      } else {
        root.toggle()
      }
    }

    Row {
      id: chip
      anchors.centerIn: parent
      spacing: Style.space(4)

      Text {
        id: glyph
        height: root.glyphBox
        text: "󰒃"
        color: root.alarming ? root.urgent : root.barForeground
        font.family: root.fontFamily
        font.pixelSize: Style.bar.iconFont
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering

        RotationAnimation on rotation {
          from: 0
          to: 360
          duration: 1400
          loops: Animation.Infinite
          running: root.scanning || root.updating
        }
      }

      Text {
        visible: !root.vertical && root.label !== ""
        height: root.glyphBox
        text: root.label
        color: root.alarming ? root.urgent : root.barForeground
        font.family: root.fontFamily
        font.pixelSize: Math.max(9, Math.round(Style.bar.iconFont * 0.92))
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onActivateRequested: {
        if (root.scanning || root.updating) root.stopWork()
        else root.scanDownloads()
      }
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.refresh()
        else if (t === "d" || t === "D") root.scanDownloads()
        else if (t === "h" || t === "H") root.scanHome()
        else if (t === "u" || t === "U") root.updateDb()
        else if (t === "x" || t === "X") root.stopWork()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: "ClamAV"
            meta: Model.phaseLabel(root.status)
            foreground: root.alarming ? root.urgent : root.foreground
            fontFamily: root.fontFamily
          }

          Column {
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              width: parent.width
              text: "SCAN"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              width: parent.width
              text: Model.scanProgressText(root.status)
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Text {
              visible: String(root.status.scan && root.status.scan.currentFile || "") !== ""
              width: parent.width
              text: String(root.status.scan.currentFile)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideMiddle
            }

            Meter {
              width: parent.width
              value: root.scanning ? root.progress : (root.status.scan && root.status.scan.percent ? root.progress : -1)
              indeterminate: root.updating || (root.scanning && root.progress <= 0)
              alarming: root.status.phase === "infected"
            }

            Row {
              width: parent.width
              spacing: Style.space(6)

              Button {
                width: (parent.width - parent.spacing) / 2
                text: "Downloads"
                iconText: "󰉍"
                foreground: root.foreground
                fontFamily: root.fontFamily
                bordered: true
                enabled: !root.scanning && !root.updating
                onClicked: root.scanDownloads()
              }

              Button {
                width: (parent.width - parent.spacing) / 2
                text: "Home"
                iconText: "󰋜"
                foreground: root.foreground
                fontFamily: root.fontFamily
                bordered: true
                enabled: !root.scanning && !root.updating
                onClicked: root.scanHome()
              }
            }

            Button {
              width: parent.width
              visible: root.scanning || root.updating
              text: root.updating ? "Cancel update" : "Stop scan"
              iconText: "󰓛"
              foreground: root.urgent
              accent: root.urgent
              fontFamily: root.fontFamily
              bordered: true
              onClicked: root.stopWork()
            }
          }

          PanelSeparator { width: parent.width; foreground: root.foreground }

          Column {
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              width: parent.width
              text: "DEFINITIONS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Item {
              width: parent.width
              implicitHeight: Math.max(dbLabel.implicitHeight, dbValue.implicitHeight)

              Text {
                id: dbLabel
                text: "Virus database"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: dbValue
                text: Model.ageText(root.status)
                color: root.alarming && root.reminderDueColor() ? root.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            Text {
              width: parent.width
              visible: !!(root.status.database && root.status.database.reminderDue)
              text: "Definitions are over a week old. Refresh them when you can."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              visible: !!(root.status.database && root.status.database.stale)
                && !(root.status.database && root.status.database.reminderDue)
              text: "Getting stale — a refresh this week would be good."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              visible: String(root.status.database && root.status.database.lastUpdateMessage || "") !== ""
              text: String(root.status.database.lastUpdateMessage)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
              elide: Text.ElideRight
              maximumLineCount: 3
            }

            Button {
              width: parent.width
              text: root.updating ? "Updating…" : "Update database"
              iconText: "󰚰"
              iconSpinning: root.updating
              foreground: root.foreground
              fontFamily: root.fontFamily
              bordered: true
              active: !!(root.status.database && root.status.database.reminderDue)
              enabled: !root.scanning && !root.updating
              onClicked: root.updateDb()
            }
          }

          PanelSeparator { width: parent.width; foreground: root.foreground }

          Column {
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              width: parent.width
              text: "STATUS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            InfoPair {
              label: "Scanner daemon"
              value: root.status.daemon && root.status.daemon.active ? "active" : "inactive"
            }
            InfoPair {
              label: "freshclam"
              value: root.status.daemon && root.status.daemon.freshclamActive ? "active" : "inactive"
            }
            InfoPair {
              visible: String(root.status.scan && root.status.scan.summary || "") !== ""
                && !root.scanning
              label: "Last scan"
              value: String(root.status.scan.summary)
            }
          }

          Column {
            id: infectedSection
            visible: root.status.scan && root.status.scan.infectedFiles
              && root.status.scan.infectedFiles.length > 0
            width: parent.width
            spacing: Style.space(6)

            PanelSeparator { width: parent.width; foreground: root.foreground }

            PanelSectionHeader {
              width: parent.width
              text: "INFECTED"
              foreground: root.urgent
              fontFamily: root.fontFamily
            }

            Repeater {
              model: root.status.scan.infectedFiles
              Text {
                required property var modelData
                width: infectedSection.width
                text: String(modelData)
                color: root.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WrapAnywhere
              }
            }
          }

          Text {
            visible: String(root.status.lastError || svc.lastError || "") !== ""
            width: parent.width
            text: String(root.status.lastError || svc.lastError)
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Text {
            width: parent.width
            topPadding: Style.space(4)
            text: "d downloads · h home · u update · x stop · r refresh"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }

  function reminderDueColor() {
    return !!(root.status.database && root.status.database.reminderDue)
  }

  component Meter: Item {
    id: meter
    property real value: -1
    property bool alarming: false
    property bool indeterminate: false
    property real thickness: Math.max(Style.space(4), Math.round(Style.spacing.controlHeight * 0.14))
    implicitHeight: thickness
    visible: value >= 0 || indeterminate

    Rectangle {
      id: meterTrack
      anchors.fill: parent
      radius: height / 2
      color: root.track
    }

    Rectangle {
      id: meterFill
      anchors.left: meterTrack.left
      anchors.verticalCenter: meterTrack.verticalCenter
      height: meterTrack.height
      radius: meterTrack.radius
      width: meter.indeterminate
        ? meterTrack.width * 0.28
        : meterTrack.width * Model.clamp(meter.value, 0, 1)
      color: meter.alarming ? root.urgent : root.foreground
      Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

      SequentialAnimation on x {
        running: meter.indeterminate && meter.visible
        loops: Animation.Infinite
        NumberAnimation {
          from: 0
          to: Math.max(0, meterTrack.width - meterFill.width)
          duration: 900
          easing.type: Easing.InOutCubic
        }
        NumberAnimation {
          from: Math.max(0, meterTrack.width - meterFill.width)
          to: 0
          duration: 900
          easing.type: Easing.InOutCubic
        }
      }
    }
  }

  component InfoPair: Item {
    property string label: ""
    property string value: ""
    width: parent ? parent.width : 0
    implicitHeight: Math.max(infoLabel.implicitHeight, infoValue.implicitHeight)

    Text {
      id: infoLabel
      text: parent.label
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: infoValue
      text: parent.value
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      horizontalAlignment: Text.AlignRight
      width: Math.min(implicitWidth, parent.width * 0.55)
      elide: Text.ElideRight
    }
  }
}
