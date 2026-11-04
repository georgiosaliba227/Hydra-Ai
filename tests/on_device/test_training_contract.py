import pytest

from ai.on_device.contract import FAMILIES, split_rows, choose_regularization


def row(identity, split, family='water', group=None):
    return {'image_id': identity, 'split': split, 'drink_family': family,
            'image_path': f'images/{identity}.jpg', 'image_sha256': 'a' * 64,
            'duplicate_group_id': group or identity, 'review_status': 'reviewed'}


def test_keeps_training_validation_and_test_separate():
    groups = split_rows([row('a', 'train'), row('b', 'validation'), row('c', 'test')])
    assert [[r['image_id'] for r in groups[s]] for s in ('train','validation','test')] == [['a'],['b'],['c']]
    assert len(FAMILIES) == 12


@pytest.mark.parametrize('change', [
    {'image_path': '../private.jpg'}, {'drink_family': 'invented'},
    {'review_status': 'unreviewed'}, {'image_sha256': 'invalid'}, {'split': 'other'},
])
def test_unreviewed_or_unbounded_inputs_rejected(change):
    item = row('a','train'); item.update(change)
    with pytest.raises(ValueError):
        split_rows([item, row('b','validation'),row('c','test')])


def test_product_group_leakage_is_rejected():
    with pytest.raises(ValueError,match='split'):
        split_rows([row('a','train',group='same'), row('b','validation',group='same'),row('c','test')])


def test_selection_uses_only_validation_and_stable_tie_break():
    assert choose_regularization([(1.0,0.6),(.1,.8),(.01,.8)]) == .01
    with pytest.raises(ValueError): choose_regularization([])
