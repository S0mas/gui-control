#pragma once

#include <QObject>
#include <QPointF>
#include <QString>

class QQuickItem;

namespace guicontrol::actions
{

struct Result
{
    bool ok = true;
    QString error;

    static Result failure(const QString& message)
    {
        return Result {false, message};
    }
};

class SignalWaiter : public QObject
{
    Q_OBJECT

public:
    using QObject::QObject;

    bool fired() const
    {
        return mFired;
    }

public slots:
    void onSignal()
    {
        mFired = true;
    }

private:
    bool mFired = false;
};

bool scrollIntoView(QQuickItem* item);
Result tap(const QPointF& scenePoint);
Result longPress(const QPointF& scenePoint, int durationMs);
Result swipe(const QPointF& from, const QPointF& to, int durationMs);
Result typeText(const QString& text);
Result pressKey(const QString& keyName);
Result screenshot(const QString& path);
Result waitSettled(int quietMs, int timeoutMs);
Result waitTransitionDone(int timeoutMs);
Result waitSelector(const QString& selector, bool present, bool includeHidden, int timeoutMs);
Result waitSignal(const QString& selector, const QString& signalName, bool includeHidden, int timeoutMs);

void spin(int milliseconds);

} // namespace guicontrol::actions
