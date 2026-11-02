#pragma once

#include <QHash>
#include <QSet>
#include <QJsonObject>
#include <QObject>

class QTcpServer;
class QTcpSocket;

namespace guicontrol
{

class ControlServer : public QObject
{
    Q_OBJECT

public:
    ControlServer(QString bindAddress, quint16 port, QObject* parent = nullptr);

    bool listen();

private:
    void onNewConnection();
    void onReadyRead(QTcpSocket* socket);
    void onDisconnected(QTcpSocket* socket);
    QJsonObject dispatch(const QJsonObject& request);

    QTcpServer* mServer;
    QString mBindAddress;
    quint16 mPort;
    QHash<QTcpSocket*, QByteArray> mBuffers;
    QSet<QTcpSocket*> mDispatching;
    QSet<QTcpSocket*> mDeleteAfterDispatch;
};

} // namespace guicontrol
