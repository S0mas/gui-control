#include "ControlServer.hpp"

#include <QGenericArgument>
#include <QHash>
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMetaObject>
#include <QQuickItem>
#include <QQuickWindow>
#include <QTcpServer>
#include <QTcpSocket>

#include "Actions.hpp"
#include "Scene.hpp"

namespace guicontrol
{
namespace
{

constexpr int DefaultTimeoutMs = 5000;
constexpr int MaxInvokeArguments = 3;
const QString BackendName = QStringLiteral("qtquick");
const QString DeclaredPropertiesMarker = QStringLiteral("*");

using Handler = QJsonObject (*)(const QJsonObject&);

QJsonObject failure(const QString& message, const QJsonArray& candidates = {})
{
    QJsonObject response {{"ok", false}, {"error", message}};
    if (!candidates.isEmpty())
    {
        response["candidates"] = candidates;
    }
    return response;
}

QJsonObject fromResult(const actions::Result& result)
{
    if (!result.ok)
    {
        return failure(result.error);
    }
    QJsonObject response {{"ok", true}};
    if (!result.error.isEmpty())
    {
        response["warning"] = result.error;
    }
    return response;
}

scene::TreeOptions treeOptions(const QJsonObject& request)
{
    scene::TreeOptions options;
    options.maxDepth = request.value("depth").toInt(-1);
    options.includeHidden = request.value("hidden").toBool(false);

    const QJsonValue props = request.value("props");
    if (request.value("all_props").toBool(false))
    {
        options.selection = scene::PropertySelection::Every;
    }
    else if (props.isArray())
    {
        options.selection = scene::PropertySelection::Listed;
        const QJsonArray names = props.toArray();
        for (const QJsonValue& name : names)
        {
            options.props.push_back(name.toString());
        }
    }
    else if (props.toString() == DeclaredPropertiesMarker)
    {
        options.selection = scene::PropertySelection::Declared;
    }
    return options;
}

bool resolvePoint(const QJsonObject& request, QPointF& point, QJsonObject& error, bool& scrolled)
{
    scrolled = false;
    if (request.contains("x") && request.contains("y"))
    {
        point = QPointF(request.value("x").toDouble(), request.value("y").toDouble());
        return true;
    }

    const QString selector = request.value("selector").toString();
    if (selector.isEmpty())
    {
        error = failure("either 'selector' or 'x'/'y' is required");
        return false;
    }

    QString message;
    QJsonArray candidates;
    QQuickItem* item = scene::resolveOne(selector, request.value("hidden").toBool(false), message, candidates);
    if (!item)
    {
        error = failure(message, candidates);
        return false;
    }

    scrolled = actions::scrollIntoView(item);
    point = scene::sceneRect(item).center();
    return true;
}

QJsonObject withScrolled(QJsonObject response, bool scrolled)
{
    if (scrolled)
    {
        response["scrolled"] = true;
    }
    return response;
}

QQuickItem* resolveItem(const QJsonObject& request, QJsonObject& error)
{
    const QString selector = request.value("selector").toString();
    if (selector.isEmpty())
    {
        error = failure("'selector' is required");
        return nullptr;
    }

    QString message;
    QJsonArray candidates;
    QQuickItem* item = scene::resolveOne(selector, request.value("hidden").toBool(false), message, candidates);
    if (!item)
    {
        error = failure(message, candidates);
    }
    return item;
}

QJsonObject handlePing(const QJsonObject& request);

QJsonObject handleTree(const QJsonObject& request)
{
    QQuickWindow* window = scene::window();
    if (!window)
    {
        return failure("no QQuickWindow available yet");
    }

    const scene::TreeOptions options = treeOptions(request);
    const QString selector = request.value("selector").toString();
    if (selector.isEmpty())
    {
        return QJsonObject {{"ok", true}, {"tree", scene::itemToJson(window->contentItem(), options)}};
    }

    QString error;
    auto parsed = scene::Selector::parse(selector, error);
    if (!parsed)
    {
        return failure(error);
    }
    parsed->includeHidden = options.includeHidden;

    QJsonArray matches;
    const auto items = scene::match(*parsed);
    for (const QQuickItem* item : items)
    {
        matches.append(scene::itemToJson(item, options));
    }
    return QJsonObject {{"ok", true}, {"matches", matches}, {"count", matches.size()}};
}

QJsonObject handleTap(const QJsonObject& request)
{
    QPointF point;
    QJsonObject error;
    bool scrolled = false;
    if (!resolvePoint(request, point, error, scrolled))
    {
        return error;
    }
    return withScrolled(fromResult(actions::tap(point)), scrolled);
}

QJsonObject handleLongPress(const QJsonObject& request)
{
    QPointF point;
    QJsonObject error;
    bool scrolled = false;
    if (!resolvePoint(request, point, error, scrolled))
    {
        return error;
    }
    return withScrolled(fromResult(actions::longPress(point, request.value("duration").toInt(0))), scrolled);
}

QJsonObject handleScroll(const QJsonObject& request)
{
    QJsonObject error;
    QQuickItem* item = resolveItem(request, error);
    if (!item)
    {
        return error;
    }
    const bool scrolled = actions::scrollIntoView(item);
    const QRectF rect = scene::sceneRect(item);
    return QJsonObject {{"ok", true}, {"scrolled", scrolled},
        {"rect", QJsonObject {{"x", rect.x()}, {"y", rect.y()}, {"width", rect.width()}, {"height", rect.height()}}}};
}

QJsonObject handleSwipe(const QJsonObject& request)
{
    QPointF from;
    QJsonObject error;
    bool scrolled = false;
    if (!resolvePoint(request, from, error, scrolled))
    {
        return error;
    }

    if (!request.contains("to_x") || !request.contains("to_y"))
    {
        return failure("'to_x' and 'to_y' are required");
    }
    const QPointF to(request.value("to_x").toDouble(), request.value("to_y").toDouble());
    return withScrolled(fromResult(actions::swipe(from, to, request.value("duration").toInt(0))), scrolled);
}

QJsonObject handleType(const QJsonObject& request)
{
    return fromResult(actions::typeText(request.value("text").toString()));
}

QJsonObject handleKey(const QJsonObject& request)
{
    return fromResult(actions::pressKey(request.value("key").toString()));
}

QJsonObject handleGet(const QJsonObject& request)
{
    QJsonObject error;
    QQuickItem* item = resolveItem(request, error);
    if (!item)
    {
        return error;
    }

    const QString name = request.value("prop").toString();
    if (name.isEmpty())
    {
        return QJsonObject {{"ok", true}, {"item", scene::itemToJson(item, treeOptions(request))}};
    }

    const QVariant value = item->property(name.toUtf8().constData());
    if (!value.isValid())
    {
        return failure(QStringLiteral("no property '%1' on %2").arg(name, scene::itemType(item)));
    }
    return QJsonObject {{"ok", true}, {"value", scene::variantToJson(value)}};
}

QJsonObject handleSet(const QJsonObject& request)
{
    QJsonObject error;
    QQuickItem* item = resolveItem(request, error);
    if (!item)
    {
        return error;
    }

    const QString name = request.value("prop").toString();
    if (name.isEmpty())
    {
        return failure("'prop' is required");
    }
    if (!item->setProperty(name.toUtf8().constData(), request.value("value").toVariant()))
    {
        return failure(QStringLiteral("could not set '%1' on %2").arg(name, scene::itemType(item)));
    }
    return QJsonObject {{"ok", true}};
}

QJsonObject handleInvoke(const QJsonObject& request)
{
    QJsonObject error;
    QQuickItem* item = resolveItem(request, error);
    if (!item)
    {
        return error;
    }

    const QString method = request.value("method").toString();
    if (method.isEmpty())
    {
        return failure("'method' is required");
    }

    const QJsonArray args = request.value("args").toArray();
    if (args.size() > MaxInvokeArguments)
    {
        return failure(QStringLiteral("at most %1 arguments are supported").arg(MaxInvokeArguments));
    }

    QVariant returned;
    QVariant a0 = args.size() > 0 ? args.at(0).toVariant() : QVariant();
    QVariant a1 = args.size() > 1 ? args.at(1).toVariant() : QVariant();
    QVariant a2 = args.size() > 2 ? args.at(2).toVariant() : QVariant();

    bool invoked = false;
    switch (args.size())
    {
    case 0:
        invoked = QMetaObject::invokeMethod(
            item, method.toUtf8().constData(), Qt::DirectConnection, Q_RETURN_ARG(QVariant, returned));
        break;
    case 1:
        invoked = QMetaObject::invokeMethod(item, method.toUtf8().constData(), Qt::DirectConnection,
            Q_RETURN_ARG(QVariant, returned), Q_ARG(QVariant, a0));
        break;
    case 2:
        invoked = QMetaObject::invokeMethod(item, method.toUtf8().constData(), Qt::DirectConnection,
            Q_RETURN_ARG(QVariant, returned), Q_ARG(QVariant, a0), Q_ARG(QVariant, a1));
        break;
    default:
        invoked = QMetaObject::invokeMethod(item, method.toUtf8().constData(), Qt::DirectConnection,
            Q_RETURN_ARG(QVariant, returned), Q_ARG(QVariant, a0), Q_ARG(QVariant, a1), Q_ARG(QVariant, a2));
        break;
    }

    if (!invoked)
    {
        return failure(QStringLiteral("could not invoke '%1' on %2").arg(method, scene::itemType(item)));
    }
    return QJsonObject {{"ok", true}, {"result", scene::variantToJson(returned)}};
}

QJsonObject handleScreenshot(const QJsonObject& request)
{
    const QString path = request.value("path").toString();
    if (path.isEmpty())
    {
        return failure("'path' is required");
    }
    const auto result = actions::screenshot(path);
    if (!result.ok)
    {
        return failure(result.error);
    }
    return QJsonObject {{"ok", true}, {"path", path}};
}

QJsonObject handleWait(const QJsonObject& request)
{
    const QString mode = request.value("mode").toString("settled");
    const int timeout = request.value("timeout").toInt(DefaultTimeoutMs);
    const bool hidden = request.value("hidden").toBool(false);

    if (mode == "settled")
    {
        return fromResult(actions::waitSettled(request.value("quiet").toInt(300), timeout));
    }
    if (mode == "transition")
    {
        return fromResult(actions::waitTransitionDone(timeout));
    }
    if (mode == "appears" || mode == "disappears")
    {
        return fromResult(
            actions::waitSelector(request.value("selector").toString(), mode == "appears", hidden, timeout));
    }
    if (mode == "signal")
    {
        return fromResult(actions::waitSignal(
            request.value("selector").toString(), request.value("signal").toString(), hidden, timeout));
    }
    return failure(QStringLiteral("unknown wait mode '%1'").arg(mode));
}

const QHash<QString, Handler>& handlers()
{
    static const QHash<QString, Handler> table {
        {QStringLiteral("ping"), &handlePing},
        {QStringLiteral("tree"), &handleTree},
        {QStringLiteral("tap"), &handleTap},
        {QStringLiteral("long_press"), &handleLongPress},
        {QStringLiteral("scroll"), &handleScroll},
        {QStringLiteral("swipe"), &handleSwipe},
        {QStringLiteral("type"), &handleType},
        {QStringLiteral("key"), &handleKey},
        {QStringLiteral("get"), &handleGet},
        {QStringLiteral("set"), &handleSet},
        {QStringLiteral("invoke"), &handleInvoke},
        {QStringLiteral("screenshot"), &handleScreenshot},
        {QStringLiteral("wait"), &handleWait},
    };
    return table;
}

QJsonObject handlePing(const QJsonObject&)
{
    QStringList ops = handlers().keys();
    ops.sort();

    QQuickWindow* window = scene::window();
    QJsonObject response {
        {"ok", true},
        {"backend", BackendName},
        {"ops", QJsonArray::fromStringList(ops)},
        {"content_props", QJsonArray::fromStringList(scene::contentProperties())},
        {"window", window != nullptr},
    };
    if (window)
    {
        response["width"] = window->width();
        response["height"] = window->height();
        response["title"] = window->title();
    }
    return response;
}

} // namespace

ControlServer::ControlServer(QString bindAddress, quint16 port, QObject* parent)
: QObject(parent)
, mServer(new QTcpServer(this))
, mBindAddress(std::move(bindAddress))
, mPort(port)
{
    connect(mServer, &QTcpServer::newConnection, this, &ControlServer::onNewConnection);
}

bool ControlServer::listen()
{
    if (!mServer->listen(QHostAddress(mBindAddress), mPort))
    {
        qWarning("[gui-control] cannot listen on %s:%u — %s", qUtf8Printable(mBindAddress), mPort,
            qUtf8Printable(mServer->errorString()));
        return false;
    }
    mPort = mServer->serverPort();
    qInfo("[gui-control] listening on %s:%u", qUtf8Printable(mBindAddress), mPort);
    return true;
}

void ControlServer::onNewConnection()
{
    while (QTcpSocket* socket = mServer->nextPendingConnection())
    {
        mBuffers.insert(socket, {});
        connect(socket, &QTcpSocket::readyRead, this, [this, socket]() { onReadyRead(socket); });
        connect(socket, &QTcpSocket::disconnected, this, [this, socket]() { onDisconnected(socket); });
    }
}

void ControlServer::onDisconnected(QTcpSocket* socket)
{
    mBuffers.remove(socket);
    if (mDispatching.contains(socket))
    {
        mDeleteAfterDispatch.insert(socket);
        return;
    }
    socket->deleteLater();
}

void ControlServer::onReadyRead(QTcpSocket* socket)
{
    if (!mBuffers.contains(socket))
    {
        return;
    }
    mBuffers[socket].append(socket->readAll());
    if (mDispatching.contains(socket))
    {
        return;
    }

    mDispatching.insert(socket);
    while (mBuffers.contains(socket))
    {
        const int newline = mBuffers[socket].indexOf('\n');
        if (newline < 0)
        {
            break;
        }
        const QByteArray line = mBuffers[socket].left(newline);
        mBuffers[socket].remove(0, newline + 1);

        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(line, &parseError);
        QJsonObject response;
        if (parseError.error != QJsonParseError::NoError || !document.isObject())
        {
            response = failure(QStringLiteral("invalid json: %1").arg(parseError.errorString()));
        }
        else
        {
            response = dispatch(document.object());
        }

        if (!mBuffers.contains(socket))
        {
            break;
        }
        socket->write(QJsonDocument(response).toJson(QJsonDocument::Compact));
        socket->write("\n");
        socket->flush();
    }
    mDispatching.remove(socket);
    if (mDeleteAfterDispatch.remove(socket))
    {
        socket->deleteLater();
    }
}

QJsonObject ControlServer::dispatch(const QJsonObject& request)
{
    const QString op = request.value("op").toString();
    const auto handler = handlers().constFind(op);
    if (handler == handlers().constEnd())
    {
        return failure(QStringLiteral("unknown op '%1'").arg(op));
    }
    return (*handler)(request);
}

} // namespace guicontrol
