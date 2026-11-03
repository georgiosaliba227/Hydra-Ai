"""Credential-free, bounded local native workers; temporary photos are never logs."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

from ai.beverage_training.MetaAdapter.cache_contract import canonical_sha256, file_sha256, strict_json, verify_cache
from scripts.train_meta_beverage_adapter import child_resident_bytes, LocalProcessError, verify_base_provenance
from .local_meta import ADAPTER_SHA256, BASE_ID, BASE_REVISION

BINARY_SHA256 = '59f248a701f4486c64ab122edfda0d5295d12e89f07766d3199140e715d2c9dd'
PROOF_SHA256 = '4054d969789f644ea36594bca2acbb109b5b2a2b1249fa150dd2c68ce2a38d9d'
ENCODER_SHA256 = '777f849b425a75d6e1910686cb8e41f9f71cdce4721c0ef5aba953571e190791'


@contextmanager
def request_lock(path: Path):
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('local_runtime_busy') from None
        yield
    finally:
        os.close(fd)


def run_bounded(command: list[str], *, timeout: float) -> None:
    """One attempt; reaped on any failure. RSS checks are sampled stop guards."""
    if timeout <= 0:
        raise ValueError('local_runtime_timeout')
    # Do not inherit provider credentials or the phone's backend token.
    env={key:os.environ[key] for key in ('HOME','TMPDIR','LANG') if key in os.environ}
    env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin'
    child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+timeout
    try:
        while child.poll() is None:
            if time.monotonic() >= deadline:
                raise ValueError('local_runtime_timeout')
            try:
                resident=child_resident_bytes(child.pid)
            except LocalProcessError:
                try: child.wait(timeout=.1)
                except subprocess.TimeoutExpired: raise ValueError('local_runtime_monitor_failed') from None
                break
            if resident>20*1024**3:
                raise ValueError('local_runtime_memory_limit')
            time.sleep(.05)
        if child.wait()!=0:
            raise ValueError('local_runtime_failed')
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()


def native_cache_arguments(descriptor: Path) -> list[str]:
    """Native decoder requires an explicit fingerprint of the admitted cache."""
    return ['--feature-cache',str(descriptor),'--feature-cache-sha256',file_sha256(descriptor)]


class LocalMetaRuntime:
    """Pinned selected checkpoint. No download client or hosted transport exists here."""
    def __init__(self, *, binary: Path, model: Path, adapter: Path, encoder: Path, ocr: Path, work_root: Path):
        if binary.is_symlink() or not binary.is_file() or file_sha256(binary)!=BINARY_SHA256:
            raise ValueError('Local camera requires the pinned executable')
        self.binary,self.model,self.adapter,self.encoder,self.ocr=binary,model,adapter,encoder,ocr
        if (adapter.is_symlink() or (adapter/'adapters.safetensors').is_symlink()
                or file_sha256(adapter/'adapters.safetensors')!=ADAPTER_SHA256):
            raise ValueError('Local camera checkpoint mismatch')
        config=strict_json((adapter/'adapter_config.json').read_text())
        if config!={'fine_tune_type':'lora','num_layers':8,'lora_parameters':{'rank':16,'scale':8,'dropout':0,'keys':['self_attn.q_proj','self_attn.v_proj']}}:
            raise ValueError('Local camera adapter configuration mismatch')
        self.adapter_config_sha=file_sha256(adapter/'adapter_config.json')
        self.encoder_config=strict_json(encoder.read_text())
        if canonical_sha256(self.encoder_config)!=ENCODER_SHA256:
            raise ValueError('Local camera encoder mismatch')
        _,proof_hash=verify_base_provenance(model,model_id=BASE_ID,revision=BASE_REVISION)
        if proof_hash!=PROOF_SHA256:
            raise ValueError('Local camera base proof mismatch')
        if ocr.is_symlink() or not ocr.is_file() or not os.access(ocr,os.X_OK):
            raise ValueError('Local label reader unavailable')
        self.work_root=work_root
        self.work_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.work_root.is_symlink() or self.work_root.stat().st_mode&0o077:
            raise ValueError('Local camera work directory must be private')
        self.lock=Path('/private/tmp/hydra-local-meta-camera.lock')
        with request_lock(self.lock):
            for entry in self.work_root.glob('request-*'):
                if entry.is_dir() and not entry.is_symlink(): shutil.rmtree(entry)
        # Check small artifacts and file identities on every request without
        # rehashing 19GB before every image. Startup hashes all base files.
        paths=[binary,ocr,encoder,adapter/'adapters.safetensors',adapter/'adapter_config.json',
               model/'base-provenance.json',*model.glob('*.safetensors'),
               *(model/name for name in ('config.json','tokenizer.json','tokenizer_config.json','processor_config.json','chat_template.jinja','generation_config.json'))]
        self.identities={path:self._identity(path) for path in paths}

    @staticmethod
    def _identity(path: Path):
        stat=path.stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)

    @classmethod
    def from_environment(cls):
        path=Path(os.environ['HYDRA_LOCAL_META_CONFIG'])
        config=strict_json(path.read_text())
        if set(config)!=set(('binary','model','adapter','encoder','ocr','work_root')):
            raise ValueError('Invalid local camera configuration')
        if any(not isinstance(value,str) or not Path(value).is_absolute() for value in config.values()):
            raise ValueError('Local camera paths must be absolute')
        return cls(**{key:Path(value) for key,value in config.items()})

    def recognize(self, jpeg: bytes) -> tuple[dict,str]:
        with request_lock(self.lock):
            if any(path.is_symlink() or self._identity(path)!=identity for path,identity in self.identities.items()):
                raise ValueError('Local camera artifact changed; restart and reverify')
            deadline=time.monotonic()+180
            with tempfile.TemporaryDirectory(prefix='request-',dir=self.work_root) as temporary:
                root=Path(temporary)
                image=root/'image.jpg'; image.write_bytes(jpeg)
                ocr=root/'label.json'
                run_bounded([str(self.ocr),str(image),str(ocr)],timeout=min(15,deadline-time.monotonic()))
                label=strict_json(ocr.read_text())
                if set(label)!={'label_text'} or not isinstance(label['label_text'],str) or len(label['label_text'])>600:
                    raise ValueError('Invalid local label evidence')
                row={'image_id':'camera-'+str(uuid4()),'image_path':'image.jpg','image_sha256':file_sha256(image),
                     'split':'validation','review_status':'reviewed'}
                rows=[row]
                manifest_hash=canonical_sha256(rows)
                policy_hash=canonical_sha256({'purpose':'live-camera-v1','image_sha256':row['image_sha256']})
                manifest=root/'vision.jsonl'; manifest.write_text(json.dumps(row)+'\n')
                encoder=root/'encoder.json'; encoder.write_text(json.dumps(self.encoder_config))
                common=['--model',str(self.model),'--data-root',str(root),'--train-manifest-sha256',manifest_hash,
                        '--source-manifest-sha256',manifest_hash,'--split-policy-sha256',policy_hash,
                        '--model-provenance-sha256',PROOF_SHA256,'--encoder-config-sha256',ENCODER_SHA256,
                        '--image-tokens','1024','--prefill-step','128','--max-output-tokens','96',
                        '--memory-limit-gb','19','--rss-limit-gb','20','--split','validation']
                features=root/'features'
                run_bounded([str(self.binary),'prepare-features',*common,'--manifest',str(manifest),
                             '--output',str(features),'--encoder-config',str(encoder)],timeout=deadline-time.monotonic())
                descriptor=features/'feature-cache.json'
                cache=verify_cache(descriptor,rows=rows,split='validation',encoder_sha256=ENCODER_SHA256,
                                   source_manifest_sha256=manifest_hash,split_policy_sha256=policy_hash)
                if cache['entries'][0]['outcome']!='success': raise ValueError('Local image encoding failed')
                # Pixel-free language input; no labels, OCR text or corrections enter Meta.
                language=root/'language.jsonl'
                language.write_text(json.dumps({key:value for key,value in row.items() if key!='image_path'})+'\n')
                output=root/'result'
                run_bounded([str(self.binary),'infer',*common,'--manifest',str(language),'--output',str(output),
                             *native_cache_arguments(descriptor),'--feature-cache-artifact-path','features/feature-cache.json',
                             '--encoder-config-artifact-path','features/encoder-config.json','--adapter',str(self.adapter)],
                            timeout=deadline-time.monotonic())
                predictions=(output/'predictions.jsonl').read_text().splitlines()
                if len(predictions)!=1: raise ValueError('Local runtime must produce one prediction')
                prediction=strict_json(predictions[0])
                if prediction.get('image_id')!=row['image_id']: raise ValueError('Local image result mismatch')
                return prediction,label['label_text']
