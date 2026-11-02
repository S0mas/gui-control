#pragma once

#include <optional>

#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QPair>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QVariant>

class QQuickItem;
class QQuickWindow;

namespace guicontrol::scene
{

QQuickWindow* window();

QString itemType(const QQuickItem* item);

QRectF sceneRect(const QQuickItem* item);

QJsonValue variantToJson(const QVariant& value);

struct TreeOptions
{
    int maxDepth = -1;
    bool includeHidden = false;
    bool allProps = false;
    QStringList props;
};

QJsonObject itemToJson(const QQuickItem* item, const TreeOptions& options, int depth = 0);

QJsonObject describe(const QQuickItem* item);

struct Segment
{
    QString type;
    QString objectName;
    QList<QPair<QString, QString>> predicates;
    int index = -1;
};

struct Selector
{
    QList<Segment> segments;
    bool includeHidden = false;

    static std::optional<Selector> parse(const QString& text, QString& error);
};

QList<QQuickItem*> match(const Selector& selector);

QQuickItem* resolveOne(const QString& selectorText, bool includeHidden, QString& error, QJsonArray& candidates);

} // namespace guicontrol::scene
