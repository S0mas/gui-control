import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window

    width: 480
    height: 640
    visible: true
    title: "gui-control demo"

    StackView {
        id: stack

        anchors.fill: parent
        initialItem: homePage
    }

    Component {
        id: homePage

        Page {
            objectName: "homePage"
            title: "Home"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Label {
                    id: counterLabel

                    property int count: 0

                    function summary(prefix) {
                        return prefix + count
                    }

                    objectName: "counterLabel"
                    text: "Clicked " + count + " times"
                }

                Button {
                    objectName: "incrementButton"
                    text: "Increment"
                    onClicked: counterLabel.count += 1
                }

                TextField {
                    objectName: "nameField"
                    placeholderText: "Your name"
                }

                Switch {
                    objectName: "darkSwitch"
                    text: "Dark"
                }

                Button {
                    objectName: "detailsButton"
                    text: "Details"
                    onClicked: stack.push(detailsPage)
                }

                ListView {
                    objectName: "fruitList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: 40
                    delegate: ItemDelegate {
                        required property int index

                        width: ListView.view.width
                        text: "Fruit " + index
                    }
                }
            }
        }
    }

    Component {
        id: detailsPage

        Page {
            objectName: "detailsPage"
            title: "Details"

            Button {
                objectName: "backButton"
                anchors.centerIn: parent
                text: "Back"
                onClicked: stack.pop()
            }
        }
    }
}
