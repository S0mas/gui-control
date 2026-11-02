#include "Scene.hpp"

#include <QColor>
#include <QGuiApplication>
#include <QMetaObject>
#include <QMetaProperty>
#include <QPointF>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSizeF>
#include <QUrl>

namespace guicontrol::scene
{
namespace
{

constexpr int MaxCandidates = 20;

bool isAnyType(const QString& type)
{
    return type.isEmpty() || type == "*";
}

QString jsonValueToString(const QJsonValue& value)
{
    if (value.isBool())
    {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    if (value.isDouble())
    {
        const double number = value.toDouble();
        if (qFuzzyCompare(number, qRound(number)))
        {
            return QString::number(qRound(number));
        }
        return QString::number(number);
    }
    return value.toString();
}

QString propertyAsString(const QQuickItem* item, const QString& name, bool& found)
{
    const QVariant value = item->property(name.toUtf8().constData());
    found = value.isValid();
    if (!found)
    {
        return {};
    }
    return jsonValueToString(variantToJson(value));
}

void collectDescendants(QQuickItem* root, bool includeHidden, QList<QQuickItem*>& out)
{
    const auto children = root->childItems();
    for (QQuickItem* child : children)
    {
        if (!includeHidden && !child->isVisible())
        {
            continue;
        }
        out.push_back(child);
        collectDescendants(child, includeHidden, out);
    }
}

bool matchesSegment(const QQuickItem* item, const Segment& segment)
{
    if (!isAnyType(segment.type) && itemType(item) != segment.type)
    {
        return false;
    }
    if (!segment.objectName.isEmpty() && item->objectName() != segment.objectName)
    {
        return false;
    }
    for (const auto& predicate : segment.predicates)
    {
        bool found = false;
        const QString actual = propertyAsString(item, predicate.first, found);
        if (!found || actual != predicate.second)
        {
            return false;
        }
    }
    return true;
}

QStringList splitSegments(const QString& text)
{
    QStringList segments;
    QString current;
    int depth = 0;
    for (const QChar character : text)
    {
        if (character == '[')
        {
            ++depth;
        }
        else if (character == ']')
        {
            --depth;
        }

        if (character == '/' && depth == 0)
        {
            segments.push_back(current.trimmed());
            current.clear();
            continue;
        }
        current.append(character);
    }
    segments.push_back(current.trimmed());
    return segments;
}

std::optional<Segment> parseSegment(const QString& text, QString& error)
{
    Segment segment;

    const int firstBracket = text.indexOf('[');
    const QString head = (firstBracket < 0 ? text : text.left(firstBracket)).trimmed();

    if (head.startsWith('#'))
    {
        segment.objectName = head.mid(1);
    }
    else if (!head.isEmpty())
    {
        const int hash = head.indexOf('#');
        if (hash >= 0)
        {
            segment.type = head.left(hash);
            segment.objectName = head.mid(hash + 1);
        }
        else
        {
            segment.type = head;
        }
    }

    int position = firstBracket;
    while (position >= 0 && position < text.size())
    {
        const int close = text.indexOf(']', position);
        if (close < 0)
        {
            error = QStringLiteral("unterminated '[' in selector segment '%1'").arg(text);
            return std::nullopt;
        }
        const QString body = text.mid(position + 1, close - position - 1).trimmed();

        bool isIndex = !body.isEmpty();
        for (const QChar character : body)
        {
            if (!character.isDigit())
            {
                isIndex = false;
                break;
            }
        }

        if (isIndex)
        {
            segment.index = body.toInt();
        }
        else
        {
            const int equals = body.indexOf('=');
            if (equals < 0)
            {
                error = QStringLiteral("predicate '%1' is not key=value").arg(body);
                return std::nullopt;
            }
            QString value = body.mid(equals + 1).trimmed();
            if (value.size() >= 2 && ((value.startsWith('"') && value.endsWith('"'))
                    || (value.startsWith('\'') && value.endsWith('\''))))
            {
                value = value.mid(1, value.size() - 2);
            }
            segment.predicates.push_back({body.left(equals).trimmed(), value});
        }

        position = text.indexOf('[', close);
    }

    return segment;
}

QList<QQuickItem*> relaxedCandidates(const Selector& selector)
{
    QQuickWindow* quickWindow = window();
    if (!quickWindow || selector.segments.isEmpty())
    {
        return {};
    }

    Segment relaxed = selector.segments.last();
    relaxed.predicates.clear();
    relaxed.index = -1;
    if (isAnyType(relaxed.type) && relaxed.objectName.isEmpty())
    {
        relaxed = selector.segments.last();
        relaxed.index = -1;
    }

    QList<QQuickItem*> all;
    collectDescendants(quickWindow->contentItem(), selector.includeHidden, all);

    QList<QQuickItem*> matches;
    for (QQuickItem* item : all)
    {
        if (matchesSegment(item, relaxed))
        {
            matches.push_back(item);
        }
    }
    return matches;
}

} // namespace

QQuickWindow* window()
{
    QQuickWindow* fallback = nullptr;
    const auto windows = QGuiApplication::topLevelWindows();
    for (QWindow* candidate : windows)
    {
        auto* quickWindow = qobject_cast<QQuickWindow*>(candidate);
        if (!quickWindow)
        {
            continue;
        }
        if (quickWindow->isVisible())
        {
            return quickWindow;
        }
        if (!fallback)
        {
            fallback = quickWindow;
        }
    }
    return fallback;
}

QString itemType(const QQuickItem* item)
{
    return QString::fromLatin1(item->metaObject()->className()).split('_').first();
}

QRectF sceneRect(const QQuickItem* item)
{
    return item->mapRectToScene(QRectF(0, 0, item->width(), item->height()));
}

QJsonValue variantToJson(const QVariant& value)
{
    switch (value.typeId())
    {
    case QMetaType::Bool:
        return value.toBool();
    case QMetaType::Int:
    case QMetaType::UInt:
    case QMetaType::LongLong:
    case QMetaType::ULongLong:
        return value.toLongLong();
    case QMetaType::Double:
    case QMetaType::Float:
        return value.toDouble();
    case QMetaType::QString:
        return value.toString();
    case QMetaType::QColor:
        return value.value<QColor>().name(QColor::HexArgb);
    case QMetaType::QUrl:
        return value.toUrl().toString();
    case QMetaType::QPointF:
    case QMetaType::QPoint:
    {
        const QPointF point = value.toPointF();
        return QJsonObject {{"x", point.x()}, {"y", point.y()}};
    }
    case QMetaType::QSizeF:
    case QMetaType::QSize:
    {
        const QSizeF size = value.toSizeF();
        return QJsonObject {{"width", size.width()}, {"height", size.height()}};
    }
    case QMetaType::QRectF:
    case QMetaType::QRect:
    {
        const QRectF rect = value.toRectF();
        return QJsonObject {{"x", rect.x()}, {"y", rect.y()}, {"width", rect.width()}, {"height", rect.height()}};
    }
    default:
        break;
    }

    if (value.canConvert<QString>())
    {
        return value.toString();
    }
    return QString::fromLatin1(value.typeName());
}

QJsonObject itemToJson(const QQuickItem* item, const TreeOptions& options, int depth)
{
    QJsonObject json;
    json["type"] = itemType(item);
    if (!item->objectName().isEmpty())
    {
        json["objectName"] = item->objectName();
    }

    const QRectF rect = sceneRect(item);
    json["rect"] = QJsonObject {
        {"x", rect.x()}, {"y", rect.y()}, {"width", rect.width()}, {"height", rect.height()}};

    if (!item->isVisible())
    {
        json["visible"] = false;
    }
    if (!item->isEnabled())
    {
        json["enabled"] = false;
    }
    if (!qFuzzyCompare(item->opacity(), 1.0))
    {
        json["opacity"] = item->opacity();
    }
    if (item->clip())
    {
        json["clip"] = true;
    }
    if (!qFuzzyIsNull(item->z()))
    {
        json["z"] = item->z();
    }

    QJsonObject properties;
    const QMetaObject* meta = item->metaObject();
    const int inherited = QQuickItem::staticMetaObject.propertyCount();
    for (int index = options.allProps ? 0 : inherited; index < meta->propertyCount(); ++index)
    {
        const QMetaProperty property = meta->property(index);
        if (!property.isReadable())
        {
            continue;
        }
        const QString name = QString::fromLatin1(property.name());
        if (!options.props.isEmpty() && !options.props.contains(name))
        {
            continue;
        }
        const QJsonValue converted = variantToJson(property.read(item));
        if (converted.isString() && converted.toString().isEmpty())
        {
            continue;
        }
        properties[name] = converted;
    }
    if (!properties.isEmpty())
    {
        json["props"] = properties;
    }

    if (options.maxDepth >= 0 && depth >= options.maxDepth)
    {
        const auto children = item->childItems();
        int hidden = 0;
        for (const QQuickItem* child : children)
        {
            if (options.includeHidden || child->isVisible())
            {
                ++hidden;
            }
        }
        if (hidden > 0)
        {
            json["truncatedChildren"] = hidden;
        }
        return json;
    }

    QJsonArray children;
    const auto childItems = item->childItems();
    for (const QQuickItem* child : childItems)
    {
        if (!options.includeHidden && !child->isVisible())
        {
            continue;
        }
        children.append(itemToJson(child, options, depth + 1));
    }
    if (!children.isEmpty())
    {
        json["children"] = children;
    }
    return json;
}

QJsonObject describe(const QQuickItem* item)
{
    QJsonObject json;
    json["type"] = itemType(item);
    json["objectName"] = item->objectName();
    const QRectF rect = sceneRect(item);
    json["rect"] = QJsonObject {
        {"x", rect.x()}, {"y", rect.y()}, {"width", rect.width()}, {"height", rect.height()}};

    const QVariant text = item->property("text");
    if (text.isValid() && !text.toString().isEmpty())
    {
        json["text"] = text.toString();
    }
    return json;
}

std::optional<Selector> Selector::parse(const QString& text, QString& error)
{
    Selector selector;
    const QStringList parts = splitSegments(text.trimmed());
    for (const QString& part : parts)
    {
        if (part.isEmpty())
        {
            continue;
        }
        const auto segment = parseSegment(part, error);
        if (!segment)
        {
            return std::nullopt;
        }
        selector.segments.push_back(*segment);
    }

    if (selector.segments.isEmpty())
    {
        error = QStringLiteral("empty selector");
        return std::nullopt;
    }
    return selector;
}

QList<QQuickItem*> match(const Selector& selector)
{
    QQuickWindow* quickWindow = window();
    if (!quickWindow)
    {
        return {};
    }

    QList<QQuickItem*> current {quickWindow->contentItem()};
    for (const Segment& segment : selector.segments)
    {
        QList<QQuickItem*> next;
        for (QQuickItem* root : current)
        {
            QList<QQuickItem*> descendants;
            collectDescendants(root, selector.includeHidden, descendants);
            for (QQuickItem* item : descendants)
            {
                if (matchesSegment(item, segment) && !next.contains(item))
                {
                    next.push_back(item);
                }
            }
        }

        if (segment.index >= 0)
        {
            if (segment.index >= next.size())
            {
                return {};
            }
            next = {next.at(segment.index)};
        }
        current = next;
        if (current.isEmpty())
        {
            return {};
        }
    }
    return current;
}

QQuickItem* resolveOne(const QString& selectorText, bool includeHidden, QString& error, QJsonArray& candidates)
{
    auto selector = Selector::parse(selectorText, error);
    if (!selector)
    {
        return nullptr;
    }
    selector->includeHidden = includeHidden;

    const QList<QQuickItem*> matches = match(*selector);
    if (matches.size() == 1)
    {
        return matches.first();
    }

    const QList<QQuickItem*> shown = matches.isEmpty() ? relaxedCandidates(*selector) : matches;
    for (int index = 0; index < shown.size() && index < MaxCandidates; ++index)
    {
        candidates.append(describe(shown.at(index)));
    }

    error = matches.isEmpty()
        ? QStringLiteral("selector '%1' matched nothing").arg(selectorText)
        : QStringLiteral("selector '%1' matched %2 items").arg(selectorText).arg(matches.size());
    return nullptr;
}

} // namespace guicontrol::scene
