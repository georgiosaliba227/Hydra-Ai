"""The collector must never promote unreviewed metadata to visual ground truth."""
from decimal import Decimal

import pytest

from ai.beverage_training.collection import (
    apply_review,
    candidate_from_product,
    printed_capacity_ml,
    source_image_url,
)


@pytest.mark.parametrize(('quantity', 'expected'), [
    ('330 ml', 330), ('33 cl', 330), ('1.5 L', 1500), ('0,5 l', 500),
    ('12 US fl oz (355 ml)', 355), ('6 x 330 ml', None), ('6×33cl', None),
    ('2 L + 50 cl', None), ('500 g', None), ('', None), ('1 serving 250 ml', None),
    ('12 fl oz', None), ('330 ml / 33 cl', None), ('100000 l', None),
])
def test_only_unambiguous_single_container_printed_metric_quantity(quantity, expected):
    assert printed_capacity_ml(quantity) == expected


def test_source_path_uses_raw_contributor_image_not_selected_crop():
    assert source_image_url('4012359114303', '2') == (
        'https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/401/235/911/4303/2.jpg'
    )
    with pytest.raises(ValueError):
        source_image_url('../private', '2')


def product():
    return {'code': '4012359114303', 'brands': 'Example', 'product_name': [
        {'lang': 'fr', 'text': 'Eau gazeuse'}, {'lang': 'en', 'text': 'Sparkling water'}],
        'quantity': '330 ml', 'rev': 7,
        'categories_tags': ['en:beverages', 'en:waters'],
        'images': [{'key': '1', 'uploader': 'photographer'},
                   {'key': '2', 'uploader': 'another'},
                   {'key': 'front_en', 'imgid': '2'}]}


def test_candidate_keeps_reference_quantity_separate_and_attributes_raw_photo():
    result = candidate_from_product(product(), source_revision='hf-revision')
    assert result['author'] == 'another'
    assert result['source_url'].endswith('/2.jpg')
    assert result['product'] == 'Sparkling water'
    assert result['capacity_ml'] is None
    assert result['reference_capacity_ml'] == 330
    assert result['reference_brand'] == 'Example'
    assert result['reference_product'] == 'Sparkling water'
    assert result['capacity_visible'] is False
    assert result['review_status'] == 'pending'
    assert result['split'] is None
    assert result['license'] == 'CC-BY-SA-3.0'


def test_non_beverage_and_unattributed_images_are_not_candidates():
    p = product(); p['categories_tags'] = ['en:cheeses']
    assert candidate_from_product(p, source_revision='r') is None
    p = product(); p['images'][1].pop('uploader')
    assert candidate_from_product(p, source_revision='r') is None


def test_review_admits_only_independent_visible_evidence_and_known_background():
    candidate = candidate_from_product(product(), source_revision='r')
    candidate.update(image_sha256='a'*64, original_sha256='a'*64, image_path='images/a.jpg')
    review = {'image_id': candidate['image_id'], 'review_status': 'reviewed',
              'brand': 'Example', 'product': 'Sparkling water',
              'identity_aliases': ['Example sparkling water'],
              'capacity_ml': 330, 'capacity_visible': True,
              'capacity_evidence': 'Front label lower right reads 330 ml.',
              'background': 'natural', 'drink_family': 'water', 'reviewer': 'independent visual review'}
    accepted = apply_review(candidate, review)
    assert accepted['capacity_ml'] == 330
    assert accepted['background'] == 'natural'
    assert candidate['capacity_ml'] is None
    for field, invalid in [('capacity_visible', False), ('capacity_evidence', ''),
                           ('background', 'unknown'), ('capacity_ml', Decimal('330.1'))]:
        with pytest.raises(ValueError):
            apply_review(candidate, {**review, field: invalid})


def test_stored_images_strip_metadata_and_hash_original_and_processed(tmp_path):
    Image = pytest.importorskip('PIL.Image', reason='optional offline collection dependency')
    from io import BytesIO
    from hashlib import sha256
    from ai.beverage_training.collection import store_image
    image = Image.new('RGB', (2000, 1000), 'red')
    exif = Image.Exif(); exif[270] = 'private source comment'
    stream = BytesIO(); image.save(stream, format='JPEG', exif=exif)
    payload = stream.getvalue(); destination = tmp_path / 'image.jpg'
    hashes = store_image(payload, destination)
    assert hashes['original_sha256'] == sha256(payload).hexdigest()
    assert hashes['image_sha256'] == sha256(destination.read_bytes()).hexdigest()
    processed = Image.open(destination)
    assert processed.size == (1600, 800)
    assert not processed.getexif()
    with pytest.raises(ValueError, match='too small'):
        small = BytesIO(); Image.new('RGB', (40, 50)).save(small, format='PNG')
        store_image(small.getvalue(), tmp_path / 'small.jpg')


def test_cached_download_never_repeats_existing_public_get(tmp_path):
    from ai.beverage_training.collection import cached_download
    calls = []
    def fetch(url):
        calls.append(url)
        return b'public image'
    destination = tmp_path / 'raw.jpg'
    cached_download('https://example.org/image.jpg', destination, fetch=fetch)
    cached_download('https://example.org/image.jpg', destination,
                    fetch=lambda _: pytest.fail('Cached source fetched again'))
    assert destination.read_bytes() == b'public image'


def test_review_retains_explicit_drink_family_for_diversity_audit():
    candidate = candidate_from_product(product(), source_revision='r')
    candidate.update(image_sha256='a'*64, original_sha256='a'*64, image_path='images/a.jpg')
    annotation = {'image_id': candidate['image_id'], 'review_status': 'reviewed',
                  'brand': 'Example', 'product': 'Sparkling water',
                  'identity_aliases': ['Example sparkling water'], 'drink_family': 'water',
                  'capacity_ml': 330, 'capacity_visible': True,
                  'capacity_evidence': 'Front label reads 330ml.',
                  'background': 'natural', 'background_detail': 'kitchen_counter',
                  'reviewer': 'independent visual review'}
    assert apply_review(candidate, annotation)['drink_family'] == 'water'
    with pytest.raises(ValueError, match='family'):
        apply_review(candidate, {**annotation, 'drink_family': 'not-classified'})


def test_local_parquet_projection_filters_non_drinks_before_image_collection(tmp_path):
    duckdb = pytest.importorskip('duckdb', reason='optional offline collection dependency')
    from ai.beverage_training.collection import project_products
    db = duckdb.connect()
    db.execute("CREATE TABLE products AS SELECT '1234567890123' AS code, 'Example' AS brands, "
               "'Water' AS product_name, '500ml' AS quantity, 1 AS rev, "
               "['en:beverages'] AS categories_tags, "
               "[{'key':'1','uploader':'author','imgid':NULL}] AS images")
    db.execute("INSERT INTO products VALUES ('9999999999999','Example','Cheese','500g',1,"
               "['en:cheeses'],[{'key':'1','uploader':'author','imgid':NULL}])")
    parquet = tmp_path / 'food.parquet'
    db.table('products').write_parquet(str(parquet))
    rows = project_products(str(parquet), limit=20)
    assert [r['product_name'] for r in rows] == ['Water']
    assert rows[0]['images'][0]['uploader'] == 'author'


def test_image_dhash_catches_resized_duplicates_despite_different_jpeg_bytes(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    from PIL import ImageDraw
    from io import BytesIO
    from ai.beverage_training.collection import store_image
    image = Image.new('RGB', (800, 800), 'white')
    draw = ImageDraw.Draw(image);draw.rectangle((100,150,500,650),fill='red')
    raw1=BytesIO();image.save(raw1,format='JPEG',quality=96)
    raw2=BytesIO();image.resize((600,600)).save(raw2,format='JPEG',quality=80)
    first=store_image(raw1.getvalue(),tmp_path/'first.jpg')
    second=store_image(raw2.getvalue(),tmp_path/'second.jpg')
    assert first['image_sha256'] != second['image_sha256']
    assert (int(first['image_dhash64'],16)^int(second['image_dhash64'],16)).bit_count() <= 2


def test_candidate_pool_balances_family_hints_without_promoting_them_to_labels():
    from ai.beverage_training.collection import balanced_candidates
    products=[]
    for i in range(8):
        p=product();p['code']=str(4000000000000+i);p['brands']='One soda brand'
        p['categories_tags']=['en:beverages','en:sodas'];products.append(p)
    p=product();p['code']='5000000000000';p['brands']='Water brand'
    p['categories_tags']=['en:beverages','en:waters'];products.append(p)
    selected=balanced_candidates(products,source_revision='r',limit=4,per_brand_limit=2)
    assert len(selected)==3
    assert {r['family_hint'] for r in selected} == {'soda','water'}
    assert all(r.get('drink_family') is None for r in selected)
    assert all(r['review_status']=='pending' for r in selected)


def test_offline_cli_persists_download_progress_without_turning_metadata_into_truth(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    import hashlib
    import json
    from pathlib import Path
    import subprocess
    import sys
    metadata = tmp_path/'products.json';metadata.write_text(json.dumps([product()]))
    candidate = candidate_from_product(product(), source_revision='r')
    raw = tmp_path/'originals'/f"{candidate['image_id']}.jpg";raw.parent.mkdir()
    Image.new('RGB',(600,400),'blue').save(raw,format='JPEG')
    script=Path(__file__).resolve().parents[2]/'scripts'/'collect_beverage_images.py'
    result=subprocess.run([sys.executable,str(script),'--data-root',str(tmp_path),'collect',
                           '--metadata',str(metadata),'--revision','r'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    progress=[json.loads(l) for l in (tmp_path/'download-progress.jsonl').read_text().splitlines()]
    assert len(progress)==1
    assert progress[0]['capacity_ml'] is None
    assert progress[0]['reference_capacity_ml']==330
    assert progress[0]['review_status']=='pending'
    assert progress[0]['original_sha256']==hashlib.sha256(raw.read_bytes()).hexdigest()
    second = product();second['code']='4012359114304'
    second_candidate=candidate_from_product(second,source_revision='r')
    Image.new('RGB',(600,400),'red').save(tmp_path/'originals'/f"{second_candidate['image_id']}.jpg",format='JPEG')
    metadata.write_text(json.dumps([second]))
    result=subprocess.run([sys.executable,str(script),'--data-root',str(tmp_path),'collect',
                           '--metadata',str(metadata),'--revision','r'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    retained=[json.loads(l) for l in (tmp_path/'candidates.jsonl').read_text().splitlines()]
    assert {row['image_id'] for row in retained}=={candidate['image_id'],second_candidate['image_id']}


@pytest.mark.parametrize(('literal','expected'), [('502.8 mL',503),('502.5 ml',503),('502.4 ml',502)])
def test_printed_fractional_metric_capacity_uses_documented_nearest_integer_ml(literal,expected):
    assert printed_capacity_ml(literal)==expected


def test_preregistered_brand_aliases_survive_independent_review():
    candidate=candidate_from_product(product(),source_revision='r')
    candidate.update(image_sha256='a'*64,original_sha256='a'*64,image_path='images/a.jpg')
    review={'image_id':candidate['image_id'],'review_status':'reviewed','brand':'Example',
            'brand_aliases':['Example Drinks'],'product':'Sparkling water','identity_aliases':['Example sparkling water'],
            'drink_family':'water','capacity_ml':330,'capacity_visible':True,'capacity_evidence':'Front reads330mL.',
            'background':'natural','background_detail':'table_surface','reviewer':'independent visual review'}
    assert apply_review(candidate,review)['brand_aliases']==['Example Drinks']


def test_local_parquet_requires_matching_pinned_proof_and_actual_content_hash(tmp_path):
    import hashlib
    from ai.beverage_training.collection import verify_local_parquet
    path=tmp_path/'food.parquet';path.write_bytes(b'public parquet fixture')
    proof={'repo':'openfoodfacts/product-database','revision':'r1','file':{'size':path.stat().st_size,
           'lfs':{'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}}
    assert verify_local_parquet(path,proof,revision='r1')['whole_file_verified'] is True
    with pytest.raises(ValueError,match='revision'):
        verify_local_parquet(path,proof,revision='different')
    path.write_bytes(b'public parquet fixturE')
    with pytest.raises(ValueError,match='hash'):
        verify_local_parquet(path,proof,revision='r1')


def test_sparse_preview_requires_explicit_optin_and_verified_completed_extents(tmp_path):
    import hashlib
    from ai.beverage_training.collection import verify_local_parquet
    path=tmp_path/'preview.parquet';prefix=b'first rows';footer=b'footerPAR1'
    path.write_bytes(prefix+b'\0'*100+footer)
    proof={'source_revision':'r1','source_expected_bytes':path.stat().st_size,
           'whole_file_verified':False,'contains_sparse_holes':True,
           'complete_prefix_bytes':len(prefix),'complete_prefix_sha256':hashlib.sha256(prefix).hexdigest(),
           'complete_footer_start':len(prefix)+100,'complete_footer_bytes':len(footer),
           'complete_footer_sha256':hashlib.sha256(footer).hexdigest()}
    with pytest.raises(ValueError,match='preview'):
        verify_local_parquet(path,proof,revision='r1')
    assert verify_local_parquet(path,proof,revision='r1',allow_preview=True)['whole_file_verified'] is False
    with path.open('r+b') as stream:stream.write(b'x')
    with pytest.raises(ValueError,match='prefix'):
        verify_local_parquet(path,proof,revision='r1',allow_preview=True)


def test_product_components_close_shared_alias_source_and_near_duplicate_edges():
    from ai.beverage_training.collection import connected_product_groups
    rows=[{'image_id':str(i),'source_product_id':f'p{i}','identity_aliases':[f'Brand product{i}']} for i in range(7)]
    rows[1]['identity_aliases']=['Brand product0','Brand second alias']
    rows[2]['identity_aliases']=['Brand second alias']
    rows[3]['source_product_id']='p2'
    rows[4]['image_dhash64']='0000000000000000'
    rows[5]['image_dhash64']='0000000000000001'
    rows[6]['image_dhash64']='0000000000000003'
    groups=connected_product_groups(rows,maximum_dhash_distance=1)
    assert {frozenset(row['image_id'] for row in group) for group in groups}=={
        frozenset({'0','1','2','3'}),frozenset({'4','5','6'})}


def full_split_rows():
    families=['water','soda','milk','tea','juice','beer']
    rows=[{'image_id':f'i{i:03}','source_product_id':f'p{i:03}',
           'identity_aliases':[f'Brand product{i}'],'drink_family':families[i%6],
           'background':'natural' if i%2 else 'plain',
           'background_detail':['in_hand','kitchen_counter','retail_shelf'][i%3],
           'split':None} for i in range(250)]
    rows[0]['required_split']='train';rows[1]['identity_aliases']=list(rows[0]['identity_aliases'])
    return rows


def test_frozen_size_assignment_keeps_train_exposure_and_all_components_together():
    from collections import Counter
    from ai.beverage_training.collection import assign_splits
    rows=full_split_rows();result=assign_splits(rows)
    assert Counter(row['split'] for row in result)=={'train':150,'validation':25,'test':75}
    assert result[0]['split']==result[1]['split']=='train'
    assert all(row['split'] is None for row in rows)
    test=[r for r in result if r['split']=='test']
    assert sum(r['background']=='natural' for r in test)>=30
    assert sum(n>=5 for n in Counter(r['drink_family'] for r in test).values())>=5
    assert len({r['background_detail'] for r in test if r['background']=='natural'})>=3
    assert assign_splits(rows)==result


def test_split_refuses_to_break_large_source_group_to_hit_numeric_targets():
    from ai.beverage_training.collection import assign_splits
    rows=full_split_rows()
    for row in rows:row['source_product_id']='one-product'
    with pytest.raises(ValueError,match='allocate'):
        assign_splits(rows)
