"""POI deduplication and label disambiguation (SRP).

Merges adjacent warps with the same label and adds compass directions
to disambiguate POIs that share labels.
"""

from collections import Counter


def dedup_warps(pois, py, px):
    """Merge adjacent warps that share the same label.

    Only warps within 2 tiles of each other AND with the same label
    are considered duplicates (e.g. a two-tile-wide staircase).
    """
    warp_kinds = ("warp", "exit", "connection")
    warps = [p for p in pois if p["kind"] in warp_kinds]
    others = [p for p in pois if p["kind"] not in warp_kinds]

    # Group nearby warps with same label using union-find
    used = [False] * len(warps)
    clusters = []
    for i, w in enumerate(warps):
        if used[i]:
            continue
        cluster = [w]
        used[i] = True
        for j in range(i + 1, len(warps)):
            if used[j] or warps[j]["label"] != w["label"]:
                continue
            for c in cluster:
                if abs(warps[j]["ty"] - c["ty"]) + abs(warps[j]["tx"] - c["tx"]) <= 2:
                    cluster.append(warps[j])
                    used[j] = True
                    break
        clusters.append(cluster)

    # Keep closest warp from each cluster
    for cluster in clusters:
        best = min(cluster, key=lambda w: abs(w["ty"] - py) + abs(w["tx"] - px))
        others.append(best)

    return others


def disambiguate_labels(pois, py, px):
    """Add compass directions to POIs that share the same label.

    Uses the map center as reference so labels stay stable as the player moves.
    """
    if not pois:
        return pois

    # Use map center as reference
    all_y = [p["ty"] for p in pois]
    all_x = [p["tx"] for p in pois]
    cy = (min(all_y) + max(all_y)) // 2
    cx = (min(all_x) + max(all_x)) // 2

    def _compass(p):
        dy = p["ty"] - cy
        dx = p["tx"] - cx
        ns = "south" if dy > 0 else "north" if dy < 0 else ""
        ew = "east" if dx > 0 else "west" if dx < 0 else ""
        if abs(dy) >= abs(dx):
            return ns or ew
        return ew or ns

    def _compass_full(p):
        dy = p["ty"] - cy
        dx = p["tx"] - cx
        ns = "north" if dy < 0 else "south" if dy > 0 else ""
        ew = "west" if dx < 0 else "east" if dx > 0 else ""
        if ns and ew:
            return f"{ns}-{ew}"
        return ns or ew or "nearby"

    # First pass: simple compass
    label_counts = Counter(p["label"] for p in pois)
    if any(c > 1 for c in label_counts.values()):
        for p in pois:
            if label_counts[p["label"]] > 1:
                p["label"] = f"{p['label']} ({_compass(p)})"

    # Second pass: if still duplicated, use full compass
    label_counts = Counter(p["label"] for p in pois)
    if any(c > 1 for c in label_counts.values()):
        for p in pois:
            if label_counts[p["label"]] > 1:
                base = p["label"].rsplit(" (", 1)[0]
                p["label"] = f"{base} ({_compass_full(p)})"

    return pois
