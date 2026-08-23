"""
scripts/cleanup_titles.py

One-shot janitor for misconfigured titles. Safe to re-run.

Pass 1 — suffix repair
  Titles like "1917 - 4.7" or "Spiderman Brand New Day - 8.5" come from
  the old raw-text fallback that baked ratings into titles. The suffix is
  stripped, the number recorded as that user's rating (/5; values above 5
  are treated as /10 and halved), the entry renamed, and metadata pulled
  from OMDb when available.

Pass 2 — exact-normalized duplicates
  Pairs whose normalized titles match exactly (punctuation/articles/word
  order ignored) are merged automatically, keeping the more complete
  entry as survivor. Near-but-not-exact matches are left for manual
  /merge decisions.

Usage:
    python scripts/cleanup_titles.py [--dry-run]
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config  # noqa: E402
from src.db.database import Database, Rating, WatchEntry  # noqa: E402
from src.services.omdb import OmdbClient  # noqa: E402

SUFFIX_RE = re.compile(r"^(.*?)\s*-\s*(\d+(?:\.\d+)?)$")


def split_suffix(title: str) -> tuple[str, float | None]:
    """'1917 - 4.7' -> ('1917', 4.7); 'Dune' -> ('Dune', None)."""
    match = SUFFIX_RE.match(title.strip())
    if not match:
        return title.strip(), None
    raw = float(match.group(2))
    score = raw / 2 if raw > 5 else raw          # /10 input auto-converted
    return match.group(1).strip(), round(max(0.0, min(5.0, score)), 2)


def omdb_query(title: str) -> str:
    """Common raw-text spellings OMDb won't hit."""
    return re.sub(r"(?i)\bspiderman\b", "spider-man", title)


def completeness(entry: WatchEntry) -> int:
    """How many useful fields are filled — used to pick merge survivors."""
    fields = (entry.poster, entry.genres, entry.plot, entry.actors,
              entry.director, entry.year, entry.imdb_id)
    return sum(1 for f in fields if (f or "").strip())


def repair_suffixes(db: Database, omdb: OmdbClient, dry_run: bool) -> None:
    print("— Pass 1: suffix repair —")
    for entry in list(db.all_entries()):
        clean, score = split_suffix(entry.title)
        if score is None or clean == entry.title:
            continue
        print(f"* '{entry.title}'  ->  '{clean}'  (+{score}/5 for {entry.user})")
        if dry_run:
            continue

        existing = db.find_by_title(clean)
        if existing and existing.id != entry.id:
            # A clean entry already exists — attach rating, fold, remove junk.
            db.upsert_rating(Rating(
                title=existing.title, user=entry.user,
                score=score, date=entry.date,
            ))
            result = db.merge_entries(existing.id, entry.id)
            print(f"  merged into '{existing.title}' ({result['moved_ratings']} moved)")
        else:
            if not db.rename_entry(entry.id, clean):
                print("  ! rename failed, skipping")
                continue
            db.upsert_rating(Rating(
                title=clean, user=entry.user, score=score, date=entry.date,
            ))
            meta = omdb.fetch(omdb_query(clean))
            if meta.imdb_id:
                db.apply_omdb(
                    entry.id,
                    poster=meta.poster,
                    genres=",".join(meta.genres),
                    year=meta.year,
                    imdb_id=meta.imdb_id or "",
                    plot=meta.plot,
                    actors=",".join(meta.actors),
                    director=meta.director,
                )
                print(f"  renamed + enriched via OMDb ({meta.year})")
            else:
                print("  renamed (no OMDb match — will retry later)")


def merge_exact_duplicates(db: Database, dry_run: bool) -> None:
    print("— Pass 2: exact-normalized duplicates —")
    pairs = db.duplicate_candidates()
    merged = 0
    for pair in pairs:
        keep_title = pair["keep"]["title"]
        dup_title = pair["duplicate"]["title"]
        if db._normalize_title(keep_title) != db._normalize_title(dup_title):
            continue  # near-match only — leave for manual /merge

        keep = db.find_by_title(keep_title)
        dup = db.find_by_title(dup_title)
        if not keep or not dup:
            continue
        # Survivor = more complete entry; tie goes to the older row.
        if completeness(dup) > completeness(keep):
            keep, dup = dup, keep

        print(f"* merging '{dup.title}' into '{keep.title}' "
              f"(score {pair['score']})")
        if dry_run:
            continue
        result = db.merge_entries(keep.id, dup.id)
        if result:
            merged += 1
            print(f"  done ({result['moved_ratings']} rating(s) moved)")
    if merged == 0:
        print("  none found")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if not config.omdb_api_key:
        sys.exit("OMDB_API_KEY is required (set it in .env)")

    db = Database(db_file=config.db_file)
    omdb = OmdbClient(api_key=config.omdb_api_key)

    repair_suffixes(db, omdb, dry_run)
    merge_exact_duplicates(db, dry_run)

    leftovers = db.duplicate_candidates()
    print(f"\nRemaining near-duplicate pairs for manual review: {len(leftovers)}")
    for pair in leftovers:
        print(f"  ? '{pair['duplicate']['title']}'  ~  '{pair['keep']['title']}' "
              f"(score {pair['score']})")


if __name__ == "__main__":
    main()
