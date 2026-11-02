"""Strict standard-library validation of local frozen-vision cache artifacts."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

POLICY = 'separate-frozen-vision-v1'
DTYPE_BYTES = {'BF16': 2, 'F16': 2, 'F32': 4, 'I32': 4}


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('cache path escapes its root')
    root = root.absolute()
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise ValueError("cache root/ancestors must not use symlinks")
    path = root / relative
    current = root
    for component in Path(relative).parts:
        current /= component
        if current.is_symlink():
            raise ValueError('cache symlinks are not allowed')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('cache artifact unavailable or outside root')
    return path


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('cache timestamp must be UTC')
    return parsed


def validate_tensor(path: Path, entry: dict, image_tokens: int) -> None:
    if path.stat().st_size > 32 * 1024 * 1024 or file_sha256(path) != entry['tensor_sha256']:
        raise ValueError('cache tensor size/hash mismatch')
    with path.open('rb') as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError('truncated safetensors prefix')
        length = struct.unpack('<Q', prefix)[0]
        if not 2 <= length <= 1024 * 1024:
            raise ValueError('invalid safetensors header length')
        raw_header = stream.read(length)
        header = strict_json(raw_header)
        payload = stream.read()
    tensors = {key: value for key, value in header.items() if key != '__metadata__'}
    if set(tensors) != {'vision_features', 'prompt_tokens'}:
        raise ValueError('cache must contain only features and fixed prompt tokens')
    expected = [('vision_features', entry['feature_dtype'], entry['feature_shape']), ('prompt_tokens', 'I32', entry['tokens_shape'])]
    ranges = []
    for key, dtype, shape in expected:
        value = tensors[key]
        if (value.get('dtype') != dtype or value.get('shape') != shape or dtype not in DTYPE_BYTES or not isinstance(value.get('shape'), list) or any(type(d) is not int for d in value['shape'])):
            raise ValueError('cache tensor dtype/shape mismatch')
        if any(type(d) is not int or d <= 0 for d in shape):
            raise ValueError('invalid tensor shape')
        count = 1
        for dimension in shape:
            count *= dimension
        start, end = value['data_offsets']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(payload) or end-start != count*DTYPE_BYTES[dtype]:
            raise ValueError('invalid tensor byte offsets')
        ranges.append((start, end))
    if entry['feature_key'] != 'vision_features' or entry['tokens_key'] != 'prompt_tokens' or entry['tokens_dtype'] != 'I32':
        raise ValueError('unexpected cache tensor keys')
    if entry['feature_dtype'] not in ('BF16', 'F16', 'F32') or len(entry['feature_shape']) != 2 or not 1 <= entry['feature_shape'][0] <= image_tokens or entry['feature_shape'][1] != 6656:
        raise ValueError('unsupported vision feature shape')
    if len(entry['tokens_shape']) != 1 or not 1 <= entry['tokens_shape'][0] <= image_tokens + 512:
        raise ValueError('unsupported prompt token shape')
    ordered = sorted(ranges)
    if ordered[0][0] != 0 or ordered[0][1] != ordered[1][0] or ordered[1][1] != len(payload):
        raise ValueError('overlapping or unaccounted tensor bytes')
    start, end = tensors['prompt_tokens']['data_offsets']
    if hashlib.sha256(payload[start:end]).hexdigest() != entry['prompt_tokens_sha256']:
        raise ValueError('fixed prompt token bytes mismatch')


def verify_cache(path: Path, *, rows: list[dict], split: str, encoder_sha256: str,
                 source_manifest_sha256: str, split_policy_sha256: str) -> dict:
    if any(parent.is_symlink() for parent in (path.absolute(), *path.absolute().parents)):
        raise ValueError('cache descriptor symlinks are not allowed')
    descriptor = strict_json(path.read_text())
    for key, expected in [('schema_version', 'beverage-feature-cache-v1'), ('execution_policy', POLICY), ('encoder_config_sha256', encoder_sha256), ('source_manifest_sha256', source_manifest_sha256), ('split_policy_sha256', split_policy_sha256), ('split', split), ('outcome', 'complete')]:
        if descriptor.get(key) != expected:
            raise ValueError('cache descriptor differs from frozen inputs/policy')
    start, completed = utc(descriptor['started_utc']), utc(descriptor['completed_utc'])
    if completed < start:
        raise ValueError('cache completion precedes creation')
    root = path.parent
    config = strict_json(safe_path(root, descriptor['encoder_config_path']).read_text())
    if canonical_sha256(config) != encoder_sha256:
        raise ValueError('encoder configuration hash mismatch')
    encoder_run = safe_path(root, descriptor['encoder_run_path'])
    if file_sha256(encoder_run) != descriptor['encoder_run_sha256']:
        raise ValueError('encoder worker evidence hash mismatch')
    evidence = strict_json(encoder_run.read_text())
    if (evidence.get('schema_version') != 'beverage-encoder-run-v1' or evidence.get('encoder_config_sha256') != encoder_sha256 or evidence.get('vision_only') is not True or evidence.get('language_loaded') is not False or set(evidence.get('loaded_weight_namespaces', [])) != {'vision_tower', 'vision_adapter', 'vision_projection'} or not start <= utc(evidence['started_utc']) <= utc(evidence['completed_utc']) <= completed):
        raise ValueError('vision-only worker evidence invalid')
    expected = {row['image_id']: row for row in rows if row['split'] == split}
    entries = descriptor.get('entries')
    if not isinstance(entries, list) or len(entries) != len(expected) or len({entry.get('image_id') for entry in entries}) != len(entries) or {entry.get('image_id') for entry in entries} != expected.keys():
        raise ValueError('cache must retain every split case exactly once')
    for entry in entries:
        row = expected[entry['image_id']]
        if entry.get('image_sha256') != row['image_sha256'] or entry.get('split') != split:
            raise ValueError('cache image/split binding mismatch')
        if entry.get('outcome') == 'error':
            if any(entry.get(key) is not None for key in ('tensor_path','tensor_sha256','feature_key','feature_dtype','feature_shape','tokens_key','tokens_dtype','tokens_shape','prompt_tokens_sha256')):
                raise ValueError('failed cache case cannot claim tensor data')
            if not isinstance(entry.get('error'), str) or not entry['error']:
                raise ValueError('failed cache case needs a sanitized reason')
            continue
        if entry.get('outcome') != 'success':
            raise ValueError('invalid cache case outcome')
        validate_tensor(safe_path(root, entry['tensor_path']), entry, config['image_tokens'])
    return descriptor
