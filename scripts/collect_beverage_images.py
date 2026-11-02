#!/usr/bin/env python3
"""Reproducible local OFF collector; no annotation is accepted automatically.

Use an isolated environment with Pillow + optional DuckDB. Raw files, snapshots,
review sheets and manifests belong outside Git. Run `--help` for commands.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai.beverage_training.collection import (apply_review, cached_download,
    candidate_from_product, balanced_candidates, project_products, verify_local_parquet, assign_splits, store_image, write_jsonl)


def discover(args):
    import duckdb
    root = args.data_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    verification = {'whole_file_verified': False}
    if args.parquet:
        if not args.source_proof:
            raise ValueError('Local Parquet requires explicit pinned --source-proof')
        proof = json.loads(args.source_proof.read_text())
        revision = args.revision or proof.get('revision', proof.get('source_revision'))
        verification = verify_local_parquet(args.parquet.resolve(), proof, revision=revision,
                                             allow_preview=args.allow_preview)
        source = str(args.parquet.resolve())
    else:
        info_path = root / 'source-dataset.json'
        info = json.loads(cached_download('https://huggingface.co/api/datasets/openfoodfacts/product-database', info_path))
        revision = args.revision or info['sha']
        source = f'https://huggingface.co/datasets/openfoodfacts/product-database/resolve/{revision}/food.parquet'
    rows = project_products(source, limit=args.limit)
    (root / 'projected-products.json').write_text(json.dumps(rows, ensure_ascii=False))
    (root / 'source-projection.json').write_text(json.dumps({
        'dataset': 'openfoodfacts/product-database', 'revision': revision, 'parquet_source': source,
        'limit': args.limit, 'metadata_license': 'ODbL-1.0', 'image_license': 'CC-BY-SA-3.0',
        'duckdb_version': duckdb.__version__, 'source_verification': verification}, indent=2))
    print(json.dumps({'products': len(rows), 'source_revision': revision}))


def collect(args):
    root = args.data_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    products = json.loads(args.metadata.read_text())
    if isinstance(products, dict):
        products = [r['row'] for r in products['rows']]
    candidates = balanced_candidates(products, source_revision=args.revision,
                                     limit=args.limit, per_brand_limit=args.per_brand_limit)
    def download(row):
        try:
            content = cached_download(row['source_url'], root / 'originals' / f"{row['image_id']}.jpg")
            relative = Path('images') / f"{row['image_id']}.jpg"
            row.update(store_image(content, root / relative))
            row['image_path'] = str(relative)
        except Exception as error:
            row['download_error'] = type(error).__name__
        return row
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as workers, (root / 'download-progress.jsonl').open('w') as progress:
        for row in workers.map(download, candidates):
            results.append(row)
            progress.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            progress.flush()
    previous_path = root / 'candidates.jsonl'
    previous = [json.loads(line) for line in previous_path.read_text().splitlines()] if previous_path.exists() else []
    combined = {row['image_id']: row for row in previous}
    combined.update({row['image_id']: row for row in results})
    results = list(combined.values())
    write_jsonl(previous_path, results)
    hashes = set(); unique = []
    for row in results:
        if row['image_sha256'] and row['image_sha256'] not in hashes:
            hashes.add(row['image_sha256']); unique.append(row)
    write_jsonl(root / 'downloaded-unique.jsonl', unique)
    print(json.dumps({'candidates': len(results), 'downloaded_unique': len(unique),
                      'failed': sum('download_error' in r for r in results)}))


def sheets(args):
    from PIL import Image, ImageDraw, ImageFont
    root = args.data_root.resolve()
    rows = [json.loads(line) for line in (root / 'downloaded-unique.jsonl').read_text().splitlines()]
    folder = root / 'contact-sheets'; folder.mkdir(exist_ok=True)
    cell_width, cell_height = 480, 580
    try: font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 17)
    except OSError: font = ImageFont.load_default()
    for first in range(0, len(rows), args.page_size):
        page = rows[first:first+args.page_size]
        output = Image.new('RGB', (cell_width*4, cell_height*((len(page)+3)//4)), 'white')
        draw = ImageDraw.Draw(output)
        for i, row in enumerate(page):
            image = Image.open(root / row['image_path']); image.thumbnail((460, 475))
            x, y = (i%4)*cell_width, (i//4)*cell_height
            output.paste(image, (x+(cell_width-image.width)//2,y))
            text = f"{first+i:03d} {row['image_id']}\n{row['brand'][:35]} {row['product'][:36]}\nREFERENCE ONLY: {row['reference_quantity']}"
            draw.multiline_text((x+5,y+480),text,fill='black',font=font)
        output.save(folder / f'{first:04d}.jpg',quality=94)
    print(json.dumps({'images': len(rows), 'sheets': str(folder)}))


def review(args):
    root = args.data_root.resolve()
    candidates = {r['image_id']: r for r in [json.loads(l) for l in (root / 'downloaded-unique.jsonl').read_text().splitlines()]}
    annotations = [json.loads(l) for l in args.annotations.read_text().splitlines()]
    if len({r['image_id'] for r in annotations}) != len(annotations):
        raise ValueError('Duplicate review annotation')
    rows = [apply_review(candidates[r['image_id']], r) for r in annotations]
    accepted = [r for r in rows if r['review_status'] == 'reviewed']
    write_jsonl(root / 'reviewed.jsonl', rows)
    write_jsonl(root / 'manifest-unsplit.jsonl', accepted)
    print(json.dumps({'reviewed': len(rows), 'admitted': len(accepted),
                      'manifest_sha256': hashlib.sha256((root/'manifest-unsplit.jsonl').read_bytes()).hexdigest()}))


def freeze(args):
    from ai.beverage_training.evaluation import freeze_split_policy, validate_manifest
    root = args.data_root.resolve()
    manifest_path, policy_path = root / 'manifest.jsonl', root / 'split-policy.json'
    if manifest_path.exists() or policy_path.exists():
        raise ValueError('Refusing to overwrite a frozen manifest or split policy')
    proof = json.loads(args.source_proof.read_text())
    verification = verify_local_parquet(args.parquet.resolve(), proof, revision=proof.get('revision'))
    if verification['whole_file_verified'] is not True:
        raise ValueError('Final freeze requires the complete hash-verified source catalog')
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    if any(row['source_revision'] != verification['revision'] for row in rows):
        raise ValueError('Manifest revision differs from verified source catalog')
    rows = assign_splits(rows, seed=args.seed)
    for row in rows:
        row['source_catalog_sha256'] = verification['source_sha256']
    policy = freeze_split_policy(rows)
    counts = validate_manifest(rows, root, policy)
    with manifest_path.open('x') as stream:
        stream.write(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n' for row in rows))
    with policy_path.open('x') as stream:
        json.dump(policy, stream, ensure_ascii=False, sort_keys=True, indent=2)
    (root / 'source-verification.json').write_text(json.dumps(verification, indent=2))
    print(json.dumps({'split_counts': counts, 'manifest_sha256': policy['manifest_sha256'],
                      'source_catalog_sha256': verification['source_sha256']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('discover', help='Pinned remote Parquet column projection, no full dataset download')
    p.add_argument('--limit', type=int, default=1800); p.add_argument('--parquet', type=Path, help='Use cached pinned food.parquet instead of fragile HTTP ranges')
    p.add_argument('--revision');p.add_argument('--source-proof',type=Path);p.add_argument('--allow-preview',action='store_true');p.set_defaults(run=discover)
    p = sub.add_parser('collect', help='Download attributed raw images; leave all pending visual review')
    p.add_argument('--metadata', type=Path, required=True);p.add_argument('--revision', required=True)
    p.add_argument('--limit', type=int, default=800);p.add_argument('--per-brand-limit', type=int, default=10);p.add_argument('--workers', type=int, default=4);p.set_defaults(run=collect)
    p = sub.add_parser('sheets', help='Create source contact sheets for independent manual review')
    p.add_argument('--page-size', type=int, default=12);p.set_defaults(run=sheets)
    p = sub.add_parser('review', help='Apply explicit transcribed visual annotations')
    p.add_argument('--annotations', type=Path, required=True);p.set_defaults(run=review)
    p = sub.add_parser('freeze', help='Verify full catalog, assign connected product groups and write immutable split files')
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--parquet',type=Path,required=True)
    p.add_argument('--source-proof',type=Path,required=True);p.add_argument('--seed',type=int,default=20261102);p.set_defaults(run=freeze)
    args = parser.parse_args();args.run(args)


if __name__ == '__main__':
    main()
