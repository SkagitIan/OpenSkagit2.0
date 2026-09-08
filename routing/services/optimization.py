import math


def distance(a, b):
    """Approximate local meters using longitude/latitude; sufficient for clustering."""
    lat = math.radians((a[1] + b[1]) / 2)
    dx = (b[0] - a[0]) * 111320 * math.cos(lat)
    dy = (b[1] - a[1]) * 110540
    return math.hypot(dx, dy)


def _route_cost(points, mode="driving", matrix=None, matrix_indexes=None):
    if len(points) < 2:
        return 0
    if matrix is not None:
        cost = sum(matrix[matrix_indexes[id(points[i])]][matrix_indexes[id(points[i + 1])]] or 10**9 for i in range(len(points) - 1))
    else:
        cost = sum(distance((points[i]["longitude"], points[i]["latitude"]), (points[i + 1]["longitude"], points[i + 1]["latitude"])) for i in range(len(points) - 1))
    if mode == "walking":
        for left, right in zip(points, points[1:]):
            if left.get("street_name") and left.get("street_name") == right.get("street_name"):
                cost -= min(cost * 0.02, 20)
    return cost


def _nearest_neighbor(items, mode, matrix=None):
    if not items:
        return []
    remaining = items[1:]
    result = [items[0]]
    while remaining:
        current = result[-1]
        current_index = items.index(current)
        next_item = min(remaining, key=lambda item: matrix[current_index][items.index(item)] if matrix else distance((current["longitude"], current["latitude"]), (item["longitude"], item["latitude"])))
        result.append(next_item)
        remaining.remove(next_item)
    return result


def _two_opt(items, mode, matrix=None):
    best = list(items)
    matrix_indexes = {id(item): index for index, item in enumerate(items)} if matrix is not None else None
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + list(reversed(best[i:j])) + best[j:]
                if _route_cost(candidate, mode, matrix, matrix_indexes) + 0.01 < _route_cost(best, mode, matrix, matrix_indexes):
                    best, improved = candidate, True
    return best


def cluster_and_order(items, target=60, mode="driving", matrix_factory=None):
    """Capacity-constrained geographic sweep followed by local route optimization."""
    valid = [item for item in items if item.get("longitude") is not None and item.get("latitude") is not None]
    if not valid:
        return []
    target = max(50, min(75, int(target)))
    count = math.ceil(len(valid) / target)
    center_lon = sum(item["longitude"] for item in valid) / len(valid)
    center_lat = sum(item["latitude"] for item in valid) / len(valid)
    valid.sort(key=lambda item: math.atan2(item["latitude"] - center_lat, item["longitude"] - center_lon))
    sizes = [len(valid) // count + (1 if i < len(valid) % count else 0) for i in range(count)]
    groups, cursor = [], 0
    for size in sizes:
        group = valid[cursor:cursor + size]
        cursor += size
        matrix = matrix_factory(group, mode) if matrix_factory else None
        ordered = _two_opt(_nearest_neighbor(group, mode, matrix), mode, matrix)
        groups.append(ordered)
    return groups
