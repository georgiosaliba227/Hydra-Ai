"""Licensed OFF source collection. Metadata never establishes visual ground truth.

Images: CC BY-SA 3.0, attributed to the contributor per raw image.
Metadata: Open Database License 1.0; retain source snapshots and attribution.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

IMAGE_LICENSE = 'CC-BY-SA-3.0'
BACKGROUNDS = {'natural', 'studio', 'plain'}
DRINK_FAMILIES = {'water', 'soda', 'juice', 'sports', 'energy', 'milk', 'plant_milk', 'tea', 'coffee', 'beer', 'wine', 'other'}
BEVERAGE_TAGS = {'en:beverages', 'en:milks', 'en:plant-based-milks'}


def printed_capacity_ml(quantity: str | None) -> int | None:
    """Parse only a single metric package quantity, never servings or multipacks.

    This parses reference metadata, not evidence that the number is visible.
    US fluid ounces without a printed metric equivalent remain unknown.
    """
    text = (quantity or '').strip().lower().replace(',', '.')
    dual = re.fullmatch(r'\d+(?:\.\d+)?\s*(?:us\s*)?fl\s*oz\s*\(([^()]*)\)', text)
    if dual:
        text = dual.group(1)
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(ml|cl|l)', text)
    if not match:
        return None
    value = Decimal(match.group(1)) * {'ml': 1, 'cl': 10, 'l': 1000}[match.group(2)]
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if 1 <= value <= 10000 else None


def source_image_url(code: str, image_id: str) -> str:
    if not re.fullmatch(r'\d{8,14}', code) or not re.fullmatch(r'\d+', image_id):
        raise ValueError('Invalid source barcode or image ID')
    parts = [code[:3], code[3:6], code[6:9], code[9:]] if len(code) > 8 else [code]
    return 'https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/' + '/'.join(parts) + f'/{image_id}.jpg'


def _name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    translations = {r['lang']: r['text'] for r in (value or []) if r.get('text')}
    return translations.get('en') or translations.get('main') or next(iter(translations.values()), '')


def candidate_from_product(product: dict, *, source_revision: str) -> dict | None:
    if not BEVERAGE_TAGS.intersection(product.get('categories_tags') or []):
        return None
    code = str(product.get('code', ''))
    images = product.get('images') or []
    if isinstance(images, dict):
        images = [dict(value, key=key) for key, value in images.items()]
    by_id = {r['key']: r for r in images if str(r.get('key', '')).isdigit()}
    fronts = [r for r in images if r.get('key') == 'front_en'] or [r for r in images if str(r.get('key', '')).startswith('front_')]
    image_id = str(fronts[0].get('imgid')) if fronts else next(iter(by_id), '')
    raw = by_id.get(image_id, {})
    if not raw.get('uploader') or not product.get('brands') or not _name(product.get('product_name')):
        return None
    try:
        source_url = source_image_url(code, image_id)
    except ValueError:
        return None
    return {
        'image_id': f'off-{code}-{image_id}', 'source_url': source_url,
        'source_product_id': f'openfoodfacts:{code}', 'source_revision': source_revision,
        'source_product_revision': product.get('rev'), 'source_image_id': image_id,
        'source_product_url': f'https://world.openfoodfacts.org/product/{code}',
        'author': raw['uploader'], 'license': IMAGE_LICENSE,
        'license_url': 'https://creativecommons.org/licenses/by-sa/3.0/',
        'metadata_license': 'ODbL-1.0', 'original_sha256': None, 'image_sha256': None,
        'image_path': None, 'brand': product['brands'].strip(), 'product': _name(product['product_name']),
        'identity_aliases': [], 'capacity_ml': None, 'capacity_visible': False,
        'capacity_evidence': '', 'reference_quantity': product.get('quantity'),
        'reference_brand': product['brands'].strip(), 'reference_product': _name(product['product_name']),
        'reference_capacity_ml': printed_capacity_ml(product.get('quantity')),
        'background': 'unknown', 'review_status': 'pending', 'split': None,
    }


def apply_review(candidate: dict, review: dict) -> dict:
    """Apply an explicit review; positive-capacity admission fails closed."""
    if review.get('image_id') != candidate['image_id']:
        raise ValueError('Review image does not match candidate')
    allowed = {'review_status', 'brand', 'product', 'identity_aliases', 'capacity_ml',
               'capacity_visible', 'capacity_evidence', 'background', 'background_detail', 'reviewer', 'review_notes', 'drink_family', 'brand_aliases'}
    result = {**candidate, **{k: v for k, v in review.items() if k in allowed}}
    if result['review_status'] not in {'reviewed', 'rejected', 'pending'}:
        raise ValueError('Invalid review status')
    if result['review_status'] == 'reviewed':
        if result.get('drink_family') not in DRINK_FAMILIES:
            raise ValueError('Accepted image requires reviewed drink family')
        if type(result['capacity_ml']) is not int or not 1 <= result['capacity_ml'] <= 10000:
            raise ValueError('Accepted capacity must be integer mL')
        if result['capacity_visible'] is not True or not result['capacity_evidence'].strip():
            raise ValueError('Accepted capacity requires independently transcribed visible evidence')
        if result['background'] not in BACKGROUNDS or not result.get('reviewer'):
            raise ValueError('Accepted image requires background review and reviewer')
        if not result.get('brand') or not result.get('product') or not result.get('identity_aliases'):
            raise ValueError('Accepted identity requires reviewed brand/product aliases')
        if not all(result.get(k) for k in ('image_path', 'original_sha256', 'image_sha256')):
            raise ValueError('Accepted image must have local content hashes')
    return result


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows))


def store_image(content: bytes, destination: Path) -> dict:
    """Decode and normalize orientation; retain the original separately."""
    from PIL import Image, ImageOps
    import io
    original_sha256 = hashlib.sha256(content).hexdigest()
    image = Image.open(io.BytesIO(content))
    image.load()
    if image.width < 300 or image.height < 300:
        raise ValueError('Source image is too small for label review')
    normalized = ImageOps.exif_transpose(image).convert('RGB')
    normalized.thumbnail((1600, 1600))
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(destination, format='JPEG', quality=94, exif=b'')
    gray = Image.open(destination).convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    dhash = sum((pixels[y*9+x] > pixels[y*9+x+1]) << (y*8+x)
                for y in range(8) for x in range(8))
    return {'original_sha256': original_sha256,
            'image_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'width': normalized.width, 'height': normalized.height,
            'image_dhash64': f'{dhash:016x}', 'dhash_algorithm': 'dhash-gray-9x8-lanczos-v1'}


def cached_download(url: str, destination: Path, *, fetch=None) -> bytes:
    """Cache one public GET. Network exceptions are reported, never retried here."""
    if destination.exists():
        return destination.read_bytes()
    if fetch is None:
        import urllib.request
        def fetch(address):
            request = urllib.request.Request(address, headers={
                'User-Agent': 'HydraAI-BeverageResearch/0.1 (licensed local training study)'})
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
    content = fetch(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.part')
    partial.write_bytes(content)
    partial.replace(destination)
    return content


def project_products(parquet_source: str, *, limit: int = 1800) -> list[dict]:
    """Read only source candidate columns under a bounded local-memory budget."""
    import duckdb
    if not 1 <= limit <= 100000:
        raise ValueError('Candidate limit must be between 1 and 100000')
    with duckdb.connect() as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='700MB'")
        cursor = db.execute("""SELECT code,brands,product_name,quantity,rev,categories_tags,images
            FROM read_parquet(?) WHERE
            (list_contains(categories_tags,'en:beverages') OR list_contains(categories_tags,'en:milks'))
            AND quantity IS NOT NULL AND brands IS NOT NULL AND images IS NOT NULL LIMIT ?""",
            [parquet_source, limit])
        names = [field[0] for field in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def balanced_candidates(products: list[dict], *, source_revision: str, limit: int = 800,
                        per_brand_limit: int = 10) -> list[dict]:
    """Round-robin source category hints; only visual review supplies final labels."""
    from collections import Counter, defaultdict, deque
    tags_by_family = {
        'wine': {'en:wines'}, 'beer': {'en:beers'}, 'coffee': {'en:coffee-drinks', 'en:iced-coffees', 'en:coffees'},
        'tea': {'en:tea-based-beverages', 'en:iced-teas', 'en:teas'},
        'energy': {'en:energy-drinks'}, 'sports': {'en:sports-drinks'},
        'plant_milk': {'en:plant-based-milks'}, 'milk': {'en:milks', 'en:flavoured-milks'},
        'juice': {'en:fruit-juices', 'en:fruit-nectars', 'en:smoothies', 'en:juices'},
        'water': {'en:waters'}, 'soda': {'en:sodas', 'en:carbonated-drinks'},
    }
    families = defaultdict(deque)
    seen = set()
    for product in products:
        row = candidate_from_product(product, source_revision=source_revision)
        if not row or not row['reference_capacity_ml'] or row['image_id'] in seen:
            continue
        seen.add(row['image_id'])
        categories = set(product.get('categories_tags') or [])
        hint = next((family for family, tags in tags_by_family.items() if categories.intersection(tags)), 'other')
        row['family_hint'] = hint
        families[hint].append(row)
    selected = []; brand_counts = Counter()
    while len(selected) < limit and any(families.values()):
        for family in sorted(families):
            while families[family]:
                row = families[family].popleft()
                brand = row['brand'].split(',')[0].strip().casefold()
                if brand_counts[brand] >= per_brand_limit:
                    continue
                selected.append(row); brand_counts[brand] += 1
                break
            if len(selected) == limit:
                break
    return selected


def verify_local_parquet(path: Path, proof: dict, *, revision: str,
                         allow_preview: bool = False) -> dict:
    """Bind local bytes to pinned proof; a sparse preview never becomes verified full data."""
    actual_revision = proof.get('revision', proof.get('source_revision'))
    if not revision or revision != actual_revision:
        raise ValueError('Parquet revision does not match pinned source proof')
    def range_sha256(start: int, length: int) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(1024*1024, remaining))
                if not chunk:
                    raise ValueError('Parquet source extent is truncated')
                digest.update(chunk); remaining -= len(chunk)
        return digest.hexdigest()
    if proof.get('contains_sparse_holes') is True:
        if not allow_preview or proof.get('whole_file_verified') is not False:
            raise ValueError('Sparse preview requires explicit preview opt-in')
        total = proof.get('source_expected_bytes')
        prefix = proof.get('complete_prefix_bytes'); footer_start = proof.get('complete_footer_start')
        footer_length = proof.get('complete_footer_bytes')
        if (any(type(x) is not int or x <= 0 for x in (total,prefix,footer_start,footer_length))
                or path.stat().st_size != total or prefix > footer_start or footer_start+footer_length != total):
            raise ValueError('Invalid sparse preview extents')
        if range_sha256(0,prefix) != proof.get('complete_prefix_sha256'):
            raise ValueError('Sparse preview prefix hash mismatch')
        if range_sha256(footer_start,footer_length) != proof.get('complete_footer_sha256'):
            raise ValueError('Sparse preview footer hash mismatch')
        return {'revision':revision,'whole_file_verified':False,'contains_sparse_holes':True}
    if proof.get('repo') != 'openfoodfacts/product-database':
        raise ValueError('Proof must identify the official source dataset')
    record = proof.get('file') or {}
    expected_sha = (record.get('lfs') or {}).get('sha256')
    if not isinstance(expected_sha,str) or not re.fullmatch('[a-f0-9]{64}',expected_sha):
        raise ValueError('Pinned full-source SHA256 proof is required')
    if path.stat().st_size != record.get('size'):
        raise ValueError('Pinned source byte count mismatch')
    actual_sha = range_sha256(0,path.stat().st_size)
    if actual_sha != expected_sha:
        raise ValueError('Pinned full-source hash mismatch')
    return {'revision':revision,'whole_file_verified':True,'source_sha256':actual_sha,
            'source_bytes':path.stat().st_size,'contains_sparse_holes':False}


def connected_product_groups(rows: list[dict], *, maximum_dhash_distance: int = 2) -> list[list[dict]]:
    """Close source, full-identity alias and conservative image-similarity edges."""
    from collections import defaultdict
    from .evaluation import normalize_identity
    if len({row['image_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate image IDs cannot be grouped')
    parents = list(range(len(rows)))
    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]; index = parents[index]
        return index
    def union(first, second):
        first, second = root(first), root(second)
        if first != second:
            parents[max(first, second)] = min(first, second)
    seen = {}
    for index, row in enumerate(rows):
        keys = [('source',row['source_product_id'])]
        if row.get('duplicate_group_id'):
            keys.append(('manual',row['duplicate_group_id']))
        keys.extend(('alias',normalize_identity(alias)) for alias in row['identity_aliases'])
        for key in keys:
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index
    fingerprints = [(index,int(row['image_dhash64'],16)) for index,row in enumerate(rows)
                    if row.get('image_dhash64')]
    for position,(index,fingerprint) in enumerate(fingerprints):
        for other,other_fingerprint in fingerprints[position+1:]:
            if (fingerprint ^ other_fingerprint).bit_count() <= maximum_dhash_distance:
                union(index,other)
    groups = defaultdict(list)
    for index,row in enumerate(rows):
        groups[root(index)].append(row)
    return sorted((sorted(group,key=lambda r:r['image_id']) for group in groups.values()),
                  key=lambda group:group[0]['image_id'])


def assign_splits(rows: list[dict], *, seed: int = 20261102,
                  counts: dict[str,int] | None = None) -> list[dict]:
    """Assign immutable product components using reviewed strata, never predictions.

    The final evaluator independently enforces counts, aliases and all diversity
    gates. This allocator refuses impossible targets rather than dividing a group.
    """
    from collections import Counter
    import random
    counts = counts or {'train':150,'validation':25,'test':75}
    if set(counts) != {'train','validation','test'} or sum(counts.values()) != len(rows):
        raise ValueError('Split target counts do not match the admitted dataset')
    groups = connected_product_groups(rows)
    forced = {i for i,g in enumerate(groups) if any(row.get('required_split') == 'train' for row in g)}
    if sum(len(groups[i]) for i in forced) > counts['train']:
        raise ValueError('Cannot allocate exposed training groups within target')
    free = [i for i in range(len(groups)) if i not in forced]
    def subset(available,target,rng):
        order = list(available);rng.shuffle(order);reachable = {0:()}
        for index in order:
            size = len(groups[index])
            for total,chosen in list(reachable.items()):
                updated = total+size
                if updated <= target and updated not in reachable:
                    reachable[updated] = (*chosen,index)
            if target in reachable:
                return set(reachable[target])
        return None
    for attempt in range(500):
        rng = random.Random(seed+attempt)
        test_groups = subset(free,counts['test'],rng)
        if test_groups is None:
            break
        test = [row for i in test_groups for row in groups[i]]
        natural = [row for row in test if row['background'] == 'natural']
        if (len(natural) < 30 or len({row['background_detail'] for row in natural}) < 3
                or sum(n >= 5 for n in Counter(row['drink_family'] for row in test).values()) < 5):
            continue
        validation_groups = subset([i for i in free if i not in test_groups],counts['validation'],rng)
        if validation_groups is None:
            continue
        assignments = {}
        for index,group in enumerate(groups):
            split = 'test' if index in test_groups else 'validation' if index in validation_groups else 'train'
            group_id = 'beverage-product-group-v1:' + hashlib.sha256(
                json.dumps([row['image_id'] for row in group]).encode()).hexdigest()[:24]
            assignments.update({row['image_id']:(split,group_id) for row in group})
        return [{**row,'split':assignments[row['image_id']][0],
                 'duplicate_group_id':assignments[row['image_id']][1]} for row in rows]
    raise ValueError('Cannot allocate complete product groups with required split sizes and diversity')
