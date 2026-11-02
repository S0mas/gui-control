#include "Actions.hpp"

#include <algorithm>
#include <cmath>
#include <ranges>

#include <QElapsedTimer>
#include <QEventLoop>
#include <QGuiApplication>
#include <QImage>
#include <QJsonArray>
#include <QKeyEvent>
#include <QLineF>
#include <QMetaMethod>
#include <QMouseEvent>
#include <QQuickItem>
#include <QQuickWindow>
#include <QStyleHints>
#include <QTimer>

#include "Scene.hpp"

namespace guicontrol::actions
{
namespace
{

constexpr int SwipePixelsPerStep = 10;
constexpr int PollIntervalMs = 50;
constexpr qreal ScrollMarginPixels = 16;
constexpr int ScrollSettleMs = 120;

quint64 eventTimestamp()
{
    static QElapsedTimer timer;
    if (!timer.isValid())
    {
        timer.start();
    }
    return static_cast<quint64>(timer.msecsSinceReference());
}

void sendMouse(QQuickWindow* window, QEvent::Type type, const QPointF& point, Qt::MouseButton button,
    Qt::MouseButtons buttons)
{
    QMouseEvent event(type, point, window->mapToGlobal(point.toPoint()), button, buttons, Qt::NoModifier);
    event.setTimestamp(eventTimestamp());
    QGuiApplication::sendEvent(window, &event);
}

void sendPress(QQuickWindow* window, const QPointF& point)
{
    sendMouse(window, QEvent::MouseButtonPress, point, Qt::LeftButton, Qt::LeftButton);
}

void sendRelease(QQuickWindow* window, const QPointF& point)
{
    sendMouse(window, QEvent::MouseButtonRelease, point, Qt::LeftButton, Qt::NoButton);
}

void sendMove(QQuickWindow* window, const QPointF& point)
{
    sendMouse(window, QEvent::MouseMove, point, Qt::NoButton, Qt::LeftButton);
}

QQuickWindow* requireWindow(Result& result)
{
    QQuickWindow* window = scene::window();
    if (!window)
    {
        result = Result::failure("no QQuickWindow available yet");
    }
    return window;
}

bool inside(const QQuickWindow* window, const QPointF& point)
{
    return QRectF(0, 0, window->width(), window->height()).contains(point);
}

int keyFromName(const QString& name, QString& text)
{
    static const QHash<QString, int> named {
        {"enter", Qt::Key_Return},
        {"return", Qt::Key_Return},
        {"escape", Qt::Key_Escape},
        {"esc", Qt::Key_Escape},
        {"backspace", Qt::Key_Backspace},
        {"delete", Qt::Key_Delete},
        {"tab", Qt::Key_Tab},
        {"space", Qt::Key_Space},
        {"up", Qt::Key_Up},
        {"down", Qt::Key_Down},
        {"left", Qt::Key_Left},
        {"right", Qt::Key_Right},
        {"home", Qt::Key_Home},
        {"end", Qt::Key_End},
        {"back", Qt::Key_Back},
    };

    const auto found = named.constFind(name.toLower());
    if (found != named.constEnd())
    {
        if (found.value() == Qt::Key_Space)
        {
            text = QStringLiteral(" ");
        }
        else if (found.value() == Qt::Key_Return)
        {
            text = QStringLiteral("\r");
        }
        return found.value();
    }

    if (name.size() == 1)
    {
        text = name;
        return name.at(0).toUpper().unicode();
    }
    return 0;
}

void sendKey(int key, const QString& text)
{
    QObject* target = QGuiApplication::focusObject();
    QQuickWindow* window = scene::window();
    QObject* receiver = target ? target : static_cast<QObject*>(window);
    if (!receiver)
    {
        return;
    }

    QKeyEvent press(QEvent::KeyPress, key, Qt::NoModifier, text);
    press.setTimestamp(eventTimestamp());
    QGuiApplication::sendEvent(receiver, &press);

    QKeyEvent release(QEvent::KeyRelease, key, Qt::NoModifier, text);
    release.setTimestamp(eventTimestamp());
    QGuiApplication::sendEvent(receiver, &release);
}

qreal scrollOffset(qreal targetStart, qreal targetEnd, qreal viewportStart, qreal viewportEnd)
{
    if (targetStart < viewportStart)
    {
        return targetStart - viewportStart - ScrollMarginPixels;
    }
    if (targetEnd > viewportEnd)
    {
        return targetEnd - viewportEnd + ScrollMarginPixels;
    }
    return 0;
}

qreal clampedContent(qreal wanted, qreal origin, qreal contentSize, qreal viewportSize)
{
    const qreal maximum = origin + std::max<qreal>(0, contentSize - viewportSize);
    return std::clamp(wanted, origin, maximum);
}

bool scrollFlickable(QQuickItem* flickable, QQuickItem* item)
{
    const QRectF viewport = scene::sceneRect(flickable);
    const QRectF target = scene::sceneRect(item);
    const qreal deltaY = scrollOffset(target.top(), target.bottom(), viewport.top(), viewport.bottom());
    const qreal deltaX = scrollOffset(target.left(), target.right(), viewport.left(), viewport.right());
    if (qFuzzyIsNull(deltaX) && qFuzzyIsNull(deltaY))
    {
        return false;
    }

    bool moved = false;
    if (!qFuzzyIsNull(deltaY))
    {
        const qreal current = flickable->property("contentY").toDouble();
        const qreal wanted = clampedContent(current + deltaY, flickable->property("originY").toDouble(),
            flickable->property("contentHeight").toDouble(), flickable->height());
        moved = flickable->setProperty("contentY", wanted) && !qFuzzyCompare(current, wanted);
    }
    if (!qFuzzyIsNull(deltaX))
    {
        const qreal current = flickable->property("contentX").toDouble();
        const qreal wanted = clampedContent(current + deltaX, flickable->property("originX").toDouble(),
            flickable->property("contentWidth").toDouble(), flickable->width());
        moved = (flickable->setProperty("contentX", wanted) && !qFuzzyCompare(current, wanted)) || moved;
    }
    return moved;
}

} // namespace

bool scrollIntoView(QQuickItem* item)
{
    bool scrolled = false;
    for (QQuickItem* ancestor = item->parentItem(); ancestor; ancestor = ancestor->parentItem())
    {
        if (!ancestor->inherits("QQuickFlickable"))
        {
            continue;
        }
        if (scrollFlickable(ancestor, item))
        {
            scrolled = true;
            spin(ScrollSettleMs);
        }
    }
    return scrolled;
}

void spin(int milliseconds)
{
    QEventLoop loop;
    QTimer::singleShot(milliseconds, &loop, &QEventLoop::quit);
    loop.exec(QEventLoop::AllEvents);
}

Result tap(const QPointF& scenePoint)
{
    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }
    if (!inside(window, scenePoint))
    {
        return Result::failure(QStringLiteral("point (%1, %2) is outside the window")
                                   .arg(scenePoint.x())
                                   .arg(scenePoint.y()));
    }

    sendPress(window, scenePoint);
    sendRelease(window, scenePoint);
    return result;
}

Result longPress(const QPointF& scenePoint, int durationMs)
{
    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }
    if (!inside(window, scenePoint))
    {
        return Result::failure(QStringLiteral("point (%1, %2) is outside the window")
                                   .arg(scenePoint.x())
                                   .arg(scenePoint.y()));
    }

    const int hinted = QGuiApplication::styleHints()->mousePressAndHoldInterval() + 50;
    const int duration = durationMs > 0 ? durationMs : hinted;

    sendPress(window, scenePoint);
    spin(duration);
    sendRelease(window, scenePoint);

    if (duration < hinted)
    {
        return Result {true, QStringLiteral("duration %1 ms is below the press-and-hold threshold of %2 ms")
                                 .arg(duration)
                                 .arg(hinted)};
    }
    return result;
}

Result swipe(const QPointF& from, const QPointF& to, int durationMs)
{
    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }
    if (from == to)
    {
        return Result::failure("swipe start and end are the same point");
    }
    if (!inside(window, from) || !inside(window, to))
    {
        return Result::failure("swipe endpoints must be inside the window");
    }

    const double distance = QLineF(from, to).length();
    const int steps = std::max(1, static_cast<int>(std::ceil(distance / SwipePixelsPerStep)));
    const QPointF delta = (to - from) / steps;
    const int duration = durationMs > 0 ? durationMs : 300;
    const int stepDelay = std::max(1, duration / steps);

    sendPress(window, from);
    for (int step = 1; step < steps; ++step)
    {
        spin(stepDelay);
        sendMove(window, from + (delta * step));
    }
    spin(stepDelay);
    sendMove(window, to);
    sendRelease(window, to);
    return result;
}

Result typeText(const QString& text)
{
    Result result;
    if (!requireWindow(result))
    {
        return result;
    }

    for (const QChar character : text)
    {
        sendKey(character.toUpper().unicode(), QString(character));
    }
    return result;
}

Result pressKey(const QString& keyName)
{
    Result result;
    if (!requireWindow(result))
    {
        return result;
    }

    QString text;
    const int key = keyFromName(keyName, text);
    if (key == 0)
    {
        return Result::failure(QStringLiteral("unknown key '%1'").arg(keyName));
    }
    sendKey(key, text);
    return result;
}

Result screenshot(const QString& path)
{
    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }

    const QImage image = window->grabWindow();
    if (image.isNull())
    {
        return Result::failure("grabWindow returned an empty image");
    }
    if (!image.save(path, "PNG"))
    {
        return Result::failure(QStringLiteral("could not write '%1'").arg(path));
    }
    return result;
}

constexpr int TransitionStartGraceMs = 32;

bool aScreenIsBeingPushedOrPopped(const QQuickItem* item)
{
    if (item->inherits("QQuickStackView") && item->property("busy").toBool())
    {
        return true;
    }
    const auto children = item->childItems();
    return std::ranges::any_of(children, [](const QQuickItem* child) { return aScreenIsBeingPushedOrPopped(child); });
}

Result waitTransitionDone(int timeoutMs)
{
    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }

    QElapsedTimer total;
    total.start();
    spin(TransitionStartGraceMs);
    while (aScreenIsBeingPushedOrPopped(window->contentItem()))
    {
        if (total.elapsed() > timeoutMs)
        {
            return Result::failure(
                QStringLiteral("a screen was still being pushed or popped after %1 ms").arg(timeoutMs));
        }
        spin(10);
    }
    return result;
}

Result waitSettled(int quietMs, int timeoutMs)
{
    Result transition = waitTransitionDone(timeoutMs);
    if (!transition.ok)
    {
        return transition;
    }

    Result result;
    QQuickWindow* window = requireWindow(result);
    if (!window)
    {
        return result;
    }

    QElapsedTimer sinceFrame;
    sinceFrame.start();
    const auto connection = QObject::connect(window, &QQuickWindow::frameSwapped, window, [&sinceFrame]() {
        sinceFrame.restart();
    });

    QElapsedTimer total;
    total.start();
    while (sinceFrame.elapsed() < quietMs)
    {
        if (total.elapsed() > timeoutMs)
        {
            QObject::disconnect(connection);
            return Result::failure(QStringLiteral("ui did not settle within %1 ms").arg(timeoutMs));
        }
        spin(10);
    }

    QObject::disconnect(connection);
    return result;
}

Result waitSelector(const QString& selector, bool present, bool includeHidden, int timeoutMs)
{
    QElapsedTimer total;
    total.start();
    while (total.elapsed() <= timeoutMs)
    {
        QString error;
        auto parsed = scene::Selector::parse(selector, error);
        if (!parsed)
        {
            return Result::failure(error);
        }
        parsed->includeHidden = includeHidden;

        const bool found = !scene::match(*parsed).isEmpty();
        if (found == present)
        {
            return {};
        }
        spin(PollIntervalMs);
    }

    return Result::failure(QStringLiteral("selector '%1' was still %2 after %3 ms")
                               .arg(selector, present ? "absent" : "present")
                               .arg(timeoutMs));
}

Result waitSignal(const QString& selector, const QString& signalName, bool includeHidden, int timeoutMs)
{
    QString error;
    QJsonArray candidates;
    QQuickItem* item = scene::resolveOne(selector, includeHidden, error, candidates);
    if (!item)
    {
        return Result::failure(error);
    }

    const QMetaObject* meta = item->metaObject();
    QMetaMethod signal;
    for (int index = 0; index < meta->methodCount(); ++index)
    {
        const QMetaMethod method = meta->method(index);
        if (method.methodType() != QMetaMethod::Signal)
        {
            continue;
        }
        if (QString::fromLatin1(method.name()) != signalName)
        {
            continue;
        }
        if (!signal.isValid() || method.parameterCount() < signal.parameterCount())
        {
            signal = method;
        }
    }

    if (!signal.isValid())
    {
        return Result::failure(QStringLiteral("no signal '%1' on %2").arg(signalName, scene::itemType(item)));
    }

    SignalWaiter waiter;
    const QMetaMethod slot = waiter.metaObject()->method(waiter.metaObject()->indexOfSlot("onSignal()"));
    const auto connection = QObject::connect(item, signal, &waiter, slot);
    if (!connection)
    {
        return Result::failure(QStringLiteral("could not connect to '%1'").arg(signalName));
    }

    QElapsedTimer total;
    total.start();
    while (!waiter.fired())
    {
        if (total.elapsed() > timeoutMs)
        {
            QObject::disconnect(connection);
            return Result::failure(
                QStringLiteral("signal '%1' did not fire within %2 ms").arg(signalName).arg(timeoutMs));
        }
        spin(10);
    }

    QObject::disconnect(connection);
    return {};
}

} // namespace guicontrol::actions
