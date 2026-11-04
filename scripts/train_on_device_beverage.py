"""Reproducible, public-data-only DINOv2 head training and Core ML export.

No download or provider client. Supply a locally downloaded pinned base and
the existing reviewed public dataset. Personal photos are never training input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai.on_device.contract import FAMILIES, split_rows, choose_regularization

BASE_REVISION = 'ed25f3a31f01632728cabb09d1542f84ab7b0056'
MODEL_ID = 'dinov2-small-beverage-v1'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import torch
    import torch.nn.functional as functional
    from PIL import Image
    from transformers import Dinov2Model
    import coremltools as ct

    source = json.loads((args.base / 'source.json').read_text())
    if source['model'] != 'facebook/dinov2-small' or source['revision'] != BASE_REVISION:
        raise ValueError('Wrong pinned public base')
    for file in source['files']:
        if digest(args.base / file['path']) != file['sha256']:
            raise ValueError('Base source hash mismatch')
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
    splits = split_rows(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(20261104)
    torch.set_num_threads(6)
    backbone = Dinov2Model.from_pretrained(args.base, local_files_only=True, attn_implementation='eager').eval()
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    backbone = backbone.to(device)
    mean = torch.tensor([.485, .456, .406], device=device).reshape(1, 3, 1, 1)
    std = torch.tensor([.229, .224, .225], device=device).reshape(1, 3, 1, 1)

    def image_tensor(row):
        path = args.data_root / row['image_path']
        if path.is_symlink() or not path.resolve().is_relative_to(args.data_root.resolve()):
            raise ValueError('Image outside explicit public dataset')
        if digest(path) != row['image_sha256']:
            raise ValueError('Public image hash mismatch')
        with Image.open(path) as image:
            pixels = np.array(image.convert('RGB').resize((224, 224), Image.Resampling.BILINEAR), dtype=np.float32) / 255
        return torch.from_numpy(pixels.transpose(2, 0, 1).copy())

    features, targets = {}, {}
    started = time.monotonic()
    with torch.inference_mode():
        for split, subset in splits.items():
            encoded = []
            for start in range(0, len(subset), 8):
                batch = torch.stack([image_tensor(row) for row in subset[start:start+8]]).to(device)
                embedding = backbone((batch - mean) / std).last_hidden_state[:, 0]
                encoded.append(functional.normalize(embedding, dim=-1).cpu().numpy())
            features[split] = np.concatenate(encoded)
            targets[split] = np.array([FAMILIES.index(row['drink_family']) for row in subset])
            print('encoded', split, len(subset), flush=True)

    def fit(lam):
        x = np.column_stack((features['train'], np.ones(len(features['train'])))).astype(np.float64)
        counts = np.bincount(targets['train'], minlength=len(FAMILIES))
        weights = 1 / np.maximum(counts[targets['train']], 1)
        weights *= len(weights) / weights.sum()
        y = np.eye(len(FAMILIES))[targets['train']]
        penalty = np.eye(x.shape[1]) * lam
        penalty[-1, -1] = 1e-8
        return np.linalg.solve(x.T @ (x * weights[:, None]) + penalty, x.T @ (y * weights[:, None])).astype(np.float32)

    def scores(split, head):
        return features[split] @ head[:-1] + head[-1]

    validation = [(lam, float(np.mean(scores('validation', fit(lam)).argmax(1) == targets['validation'])))
                  for lam in (.001, .01, .1, 1., 10.)]
    selected = choose_regularization(validation)
    head = fit(selected)
    np.savez(args.output/'head.npz', coefficients=head, **{key: value for key,value in features.items()})

    class PhoneModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = backbone.to('cpu')
            self.register_buffer('mean', mean.cpu())
            self.register_buffer('std', std.cpu())
            self.register_buffer('weight', torch.from_numpy(head[:-1]))
            self.register_buffer('bias', torch.from_numpy(head[-1]))

        def forward(self, image):
            features = self.encoder((image-self.mean)/self.std).last_hidden_state[:, 0]
            features = functional.normalize(features, dim=-1)
            return features @ self.weight + self.bias

    model = PhoneModel().eval()
    sample = image_tensor(splits['validation'][0]).unsqueeze(0)
    # DINOv2 traces bicubic positional interpolation even for a fixed input.
    # Core ML cannot convert that operator. Precompute exactly the same 224px
    # positions once; the exported image boundary is deliberately fixed-size.
    class FixedEmbeddings(torch.nn.Module):
        def __init__(self, original):
            super().__init__()
            self.patch_embeddings = original.patch_embeddings
            self.cls_token = original.cls_token
            self.dropout = original.dropout
            with torch.no_grad():
                positions = original.interpolate_pos_encoding(torch.zeros(1,257,384),224,224)
            self.register_buffer('positions',positions.detach())

        def forward(self, pixel_values, bool_masked_pos=None):
            patches = self.patch_embeddings(pixel_values)
            tokens = torch.cat((self.cls_token.expand(pixel_values.shape[0],-1,-1),patches),dim=1)
            return self.dropout(tokens+self.positions)

    with torch.inference_mode():
        original_scores = model(sample)
        model.encoder.embeddings = FixedEmbeddings(model.encoder.embeddings)
        if not torch.allclose(original_scores,model(sample),atol=1e-6,rtol=1e-5):
            raise ValueError('Fixed-resolution embedding parity failed')
    traced = torch.jit.trace(model, sample, check_trace=False)
    package = ct.convert(traced, convert_to='mlprogram',
                         inputs=[ct.ImageType(name='image', shape=(1,3,224,224), scale=1/255, color_layout=ct.colorlayout.RGB)],
                         outputs=[ct.TensorType(name='scores')], minimum_deployment_target=ct.target.iOS17,
                         compute_precision=ct.precision.FLOAT16)
    package.short_description = 'Meta DINOv2 Small with a public-beverage category head. Suggestions require confirmation.'
    package.author = 'Hydra AI; Meta DINOv2 backbone'
    package.license = 'Apache-2.0 backbone; see bundled model notice and dataset attribution.'
    package.version = MODEL_ID
    package.user_defined_metadata.update({'hydra.model_id': MODEL_ID, 'hydra.base_revision': BASE_REVISION,
                                         'hydra.families': json.dumps(FAMILIES), 'hydra.manifest_sha256': digest(args.manifest)})
    package_path = args.output / 'HydraBeverage.mlpackage'
    package.save(package_path)
    parity = []
    for row in splits['validation'][:3]:
        with Image.open(args.data_root / row['image_path']) as image:
            resized = image.convert('RGB').resize((224,224), Image.Resampling.BILINEAR)
        with torch.inference_mode():
            expected = model(image_tensor(row).unsqueeze(0)).numpy()
        actual = package.predict({'image': resized})['scores']
        error = float(np.max(np.abs(actual - expected)))
        if error > .03 or actual.argmax() != expected.argmax():
            raise ValueError('Core ML numerical parity failed')
        parity.append({'image_id':row['image_id'],'max_absolute_score_error':error})
    metrics = {}
    predictions = []
    for split in ('train', 'validation', 'test'):
        output = scores(split, head)
        ranking = np.sort(output,axis=1)
        admitted = (ranking[:,-1] >= .35) & ((ranking[:,-1]-ranking[:,-2]) >= .10)
        correct = output.argmax(1) == targets[split]
        metrics[split] = {'count': len(output), 'category_top1_accuracy':float(correct.mean()),
                          'suggestion_coverage':float(admitted.mean()),
                          'accepted_category_accuracy':float(correct[admitted].mean()) if admitted.any() else None}
        for index,row in enumerate(splits[split]):
            predictions.append({'image_id':row['image_id'],'split':split,'reference_family':row['drink_family'],
                                'suggested_family':FAMILIES[int(output[index].argmax())], 'admitted':bool(admitted[index])})
    files = [{'path':str(path.relative_to(package_path)), 'sha256':digest(path), 'bytes':path.stat().st_size}
             for path in sorted(package_path.rglob('*')) if path.is_file()]
    report = {'model_id':MODEL_ID,'base':source,'manifest_sha256':digest(args.manifest),'families':FAMILIES,
              'input':{'name':'image','width':224,'height':224,'resize':'full_image_bilinear_square',
                       'color':'RGB','scale':1/255,'mean':[.485,.456,.406],'std':[.229,.224,.225]},
              'output':{'name':'scores','shape':[1,12],'calibrated_probability':False,
                        'minimum_score':.35,'minimum_margin':.10},
              'fit':{'method':'class_balanced_ridge','selected_regularization':selected,
                     'validation_candidates':validation,'train_count':len(splits['train'])},
              'metrics':metrics,'coreml_parity':parity,'package_files':files,
              'package_bytes':sum(file['bytes'] for file in files),'elapsed_seconds':time.monotonic()-started,
              'limitations':['Small packaged-beverage cohort; no validated open-world/non-beverage rejection.',
                             'Category evaluation only; does not measure brand, size, liquid fill or consumption accuracy.',
                             'Sparse classes and natural cups need additional data.']}
    (args.output / 'model-metadata.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output / 'predictions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in predictions))
    print(json.dumps({'metrics':metrics,'package_bytes':report['package_bytes'],'coreml_parity':parity}),flush=True)


if __name__ == '__main__':
    main()
