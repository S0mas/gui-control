#include <QCoreApplication>
#include <QGuiApplication>
#include <QStyleHints>

#include "ControlServer.hpp"

namespace
{

constexpr quint16 DefaultPort = 7801;
const QString DefaultBindAddress = QStringLiteral("127.0.0.1");

void startControlServer()
{
    if (qEnvironmentVariable("GUI_CONTROL_ENABLED", "1") == "0")
    {
        return;
    }

    if (!qobject_cast<QGuiApplication*>(QCoreApplication::instance()))
    {
        qInfo("[gui-control] not a GUI application, staying out of the way");
        return;
    }

    const int configured = qEnvironmentVariableIntValue("GUI_CONTROL_PORT");
    const auto port = static_cast<quint16>(configured > 0 ? configured : DefaultPort);
    const QString bindAddress = qEnvironmentVariable("GUI_CONTROL_BIND", DefaultBindAddress);

    if (qEnvironmentVariable("GUI_CONTROL_BLINKING_CARET", "0") == "0")
    {
        QGuiApplication::styleHints()->setCursorFlashTime(0);
    }

    auto* server = new guicontrol::ControlServer(bindAddress, port, QCoreApplication::instance());
    if (!server->listen())
    {
        delete server;
    }
}

} // namespace

Q_COREAPP_STARTUP_FUNCTION(startControlServer)
