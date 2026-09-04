"""
Combine items from all three Phase 2 sources (GKToday, The Hindu, PIB) into
one list, tagging each with where it came from and collapsing cross-source
duplicates (the same real-world event reported by more than one source).

Cross-source dedup reuses dedup.py's fuzzy title matching rather than a
separate implementation — a story GKToday and The Hindu both covered today
should show up once, not twice. When two items collide we keep whichever
one has richer text (a non-empty excerpt beats an empty one), and prefer
GKToday's category tag since it's the most consistently curated of the
three for SSC-style bucketing.
"""

from dedup import normalize
from difflib import SequenceMatcher

CROSS_SOURCE_SIMILARITY_THRESHOLD = 0.82

# Preference order when the same story appears in multiple sources and we
# have to pick one category tag to keep.
SOURCE_PRIORITY = {"gktoday": 0, "hindu": 1, "pib": 2}


def _richness(item: dict) -> int:
    return len(item.get("excerpt", "")) + len(item.get("title", ""))


def merge(gktoday_items: list[dict], hindu_items: list[dict], pib_items: list[dict]) -> list[dict]:
    tagged: list[dict] = []
    for item in gktoday_items:
        tagged.append({**item, "source": "gktoday"})
    for item in hindu_items:
        tagged.append({**item, "source": "hindu"})
    for item in pib_items:
        tagged.append({**item, "source": "pib"})

    merged: list[dict] = []
    norm_cache: list[str] = []

    for item in tagged:
        norm = normalize(item.get("one_liner") or item.get("title", ""))
        dup_index = None
        for idx, existing_norm in enumerate(norm_cache):
            if SequenceMatcher(None, norm, existing_norm).ratio() >= CROSS_SOURCE_SIMILARITY_THRESHOLD:
                dup_index = idx
                break

        if dup_index is None:
            merged.append(item)
            norm_cache.append(norm)
            continue

        # Collision: keep the richer / higher-priority item, but don't lose
        # either source's URL — attach the alternate as "also_reported_by".
        existing = merged[dup_index]
        existing_priority = SOURCE_PRIORITY.get(existing["source"], 99)
        new_priority = SOURCE_PRIORITY.get(item["source"], 99)
        keep_new = _richness(item) > _richness(existing) or (
            _richness(item) == _richness(existing) and new_priority < existing_priority
        )
        winner, loser = (item, existing) if keep_new else (existing, item)
        winner = dict(winner)
        also = set(winner.get("also_reported_by", []))
        also.add(loser["source"])
        winner["also_reported_by"] = sorted(also)
        merged[dup_index] = winner

    return merged


if __name__ == "__main__":
    # Quick manual check with fake data
    gk = [{"title": "RBI hikes repo rate by 25 bps", "excerpt": "The RBI raised rates.",
           "category": "economy", "url": "http://gk/1"}]
    hindu = [{"title": "RBI hikes repo rate by 25 basis points", "excerpt": "",
              "category": "economy", "url": "http://hindu/1"}]
    pib = []
    for m in merge(gk, hindu, pib):
        print(m)
