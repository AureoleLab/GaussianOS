import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    visible: true; width: 1360; height: 840; minimumWidth: 1000; minimumHeight: 650
    title: "Gaussian Factory - P2"
    property var current: JSON.parse(backend.currentJson || "{}")
    property var scene: JSON.parse(backend.viewerJson || "{}")
    Connections {
        target: backend
        function onChanged() { current = JSON.parse(backend.currentJson || "{}"); scene = JSON.parse(backend.viewerJson || "{}"); }
    }
    FileDialog {
        id: inputPicker
        title: "Import video or select an image"
        onAccepted: backend.importInput(selectedFile.toString().replace("file:///", ""))
    }
    FolderDialog {
        id: folderPicker
        title: "Import image folder"
        onAccepted: backend.importInput(selectedFolder.toString().replace("file:///", ""))
    }
    header: ToolBar { RowLayout { anchors.fill: parent; anchors.margins: 8
        Label { text: "Gaussian Factory"; font.bold: true; font.pixelSize: 18; Layout.rightMargin: 20 }
        Button { text: "New project"; onClicked: projectDialog.open() }
        Button { text: "Import video"; enabled: current.project_id !== undefined; onClicked: inputPicker.open() }
        Button { text: "Import images"; enabled: current.project_id !== undefined; onClicked: folderPicker.open() }
        Item { Layout.fillWidth: true }
        Button { text: "Start / Resume"; enabled: current.input_path !== undefined; onClicked: backend.start() }
        Button { text: "Cancel"; enabled: current.status === "running"; onClicked: backend.cancel() }
    }}
    Dialog { id: projectDialog; title: "New project"; modal: true; standardButtons: Dialog.Ok | Dialog.Cancel
        property string initialRoot: ""
        contentItem: ColumnLayout {
            spacing: 8
            TextField { id: projectName; placeholderText: "Project name"; Layout.fillWidth: true }
            TextField { id: projectRoot; placeholderText: "Project folder (for example D:/Projects/scan)"; Layout.fillWidth: true }
        }
        onAccepted: backend.createProject(projectName.text, projectRoot.text)
    }
    SplitView { anchors.fill: parent
        ListView { SplitView.preferredWidth: 250; clip: true; model: JSON.parse(backend.projectsJson || "[]")
            delegate: ItemDelegate { width: ListView.view.width; text: modelData.name + "\n" + modelData.status; highlighted: modelData.project_id === current.project_id; onClicked: backend.selectProject(modelData.project_id) }
        }
        ColumnLayout { SplitView.fillWidth: true; SplitView.fillHeight: true; anchors.margins: 14; spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Label { text: current.name || "No project selected"; font.pixelSize: 22; font.bold: true }
                Item { Layout.fillWidth: true }
                Label { text: "Status: " + (current.status || "idle") }
            }
            RowLayout { Layout.fillWidth: true
                Label { text: "Mode" }
                ComboBox { id: mode; model: ["preview", "balanced", "quality"]; currentIndex: Math.max(0, model.indexOf(current.profile || "balanced")); onActivated: backend.setProfile(currentText) }
                Label { text: current.input_path ? "Input: " + current.input_path : "Import a video or image folder to begin"; elide: Label.ElideMiddle; Layout.fillWidth: true }
            }
            ProgressBar { Layout.fillWidth: true; value: { var s=current.stages||{}; var n=0; for (var x in s) if(s[x].status==="succeeded") ++n; return n/6 } }
            RowLayout { Repeater { model: ["ingest", "colmap", "fallback", "train", "validate", "export"]; delegate: Label { required property string modelData; text: modelData + ": " + ((current.stages||{})[modelData] ? current.stages[modelData].status : "pending"); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } } }
            Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "#15191e"; radius: 6
                Canvas {
                    id: canvas
                    anchors.fill: parent
                    onPaint: {
                        var c=getContext("2d"); c.fillStyle="#15191e"; c.fillRect(0,0,width,height)
                        function dots(a,color,r) { c.fillStyle=color; for(var i=0;i<a.length;i++) { c.beginPath(); c.arc(20+a[i][0]*(width-40),height-20-a[i][1]*(height-40),r,0,Math.PI*2); c.fill() } }
                        dots(scene.points||[], "#69b7ff", 1.2)
                        var a=scene.cameras||[]
                        if(a.length) { c.strokeStyle="#ffb86b"; c.lineWidth=2; c.beginPath(); for(var j=0;j<a.length;j++) { var x=20+a[j][0]*(width-40),y=height-20-a[j][1]*(height-40); if(j) c.lineTo(x,y); else c.moveTo(x,y) } c.stroke(); dots(a,"#ffb86b",3) }
                    }
                    Connections { target: backend; function onChanged() { canvas.requestPaint() } }
                }
                Label { anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 10; color: "white"; text: "Viewer - orange: camera trajectory, blue: point cloud / Gaussians" }
                Button { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8; text: "Load viewer"; onClicked: backend.loadViewer() }
            }
            TextArea { Layout.fillWidth: true; Layout.preferredHeight: 150; readOnly: true; text: backend.logText; wrapMode: TextArea.Wrap; background: Rectangle { color: "#20262d" } }
        }
    }
}
