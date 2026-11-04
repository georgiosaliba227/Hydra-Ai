"""Pure split/selection boundary, independent of optional training dependencies."""
import math
from pathlib import PurePosixPath
import re

FAMILIES = ('beer', 'coffee', 'energy', 'juice', 'milk', 'other', 'plant_milk',
            'soda', 'sports', 'tea', 'water', 'wine')


def split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    result = {key: [] for key in ('train', 'validation', 'test')}
    identities: set[str] = set()
    groups: dict[str, str] = {}
    for row in rows:
        split = row.get('split')
        path = PurePosixPath(row.get('image_path', ''))
        identity = row.get('image_id')
        if (split not in result or row.get('drink_family') not in FAMILIES
                or row.get('review_status') != 'reviewed'
                or not isinstance(identity, str) or not identity or identity in identities
                or path.is_absolute() or '..' in path.parts or len(path.parts) != 2 or path.parts[0] != 'images'
                or not re.fullmatch('[0-9a-f]{64}', row.get('image_sha256', ''))):
            raise ValueError('Invalid reviewed image/split')
        group = row.get('duplicate_group_id', identity)
        if groups.setdefault(group, split) != split:
            raise ValueError('Product group crosses split')
        identities.add(identity)
        result[split].append(row)
    if any(not rows for rows in result.values()):
        raise ValueError('All three splits required')
    return result


def choose_regularization(validation_scores: list[tuple[float, float]]) -> float:
    if not validation_scores or any(not math.isfinite(lam) or lam <= 0
                                   or not math.isfinite(score) or not 0 <= score <= 1
                                   for lam, score in validation_scores):
        raise ValueError('Invalid validation-only selection')
    return min(validation_scores, key=lambda pair: (-pair[1], pair[0]))[0]
