import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('cache_contract',Path(__file__).resolve().parents[1]/'cache_contract.py')
cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)

class CacheContractTests(unittest.TestCase):
    def fixture(self,root):
        features=bytes(6656*4);tokens=struct.pack('<4i',1,12,2,3)
        header={'vision_features':{'dtype':'F32','shape':[1,6656],'data_offsets':[0,len(features)]},'prompt_tokens':{'dtype':'I32','shape':[4],'data_offsets':[len(features),len(features)+len(tokens)]}}
        h=json.dumps(header,separators=(',',':')).encode();h+=b' '*((-len(h))%8)
        tensor=struct.pack('<Q',len(h))+h+features+tokens;(root/'sample.safetensors').write_bytes(tensor)
        config={'schema_version':'beverage-encoder-config-v1','execution_policy':'separate-frozen-vision-v1','image_tokens':512}
        (root/'encoder-config.json').write_text(json.dumps(config)); enc=cache.canonical_sha256(config)
        run={'schema_version':'beverage-encoder-run-v1','encoder_config_sha256':enc,'vision_only':True,'language_loaded':False,'loaded_weight_namespaces':['vision_adapter','vision_projection','vision_tower'],'started_utc':'2026-11-02T12:00:00Z','completed_utc':'2026-11-02T12:01:00Z'}
        (root/'encoder-run.json').write_text(json.dumps(run))
        entry={'image_id':'a','image_sha256':'a'*64,'split':'train','outcome':'success','error':None,'tensor_path':'sample.safetensors','tensor_sha256':hashlib.sha256(tensor).hexdigest(),'feature_key':'vision_features','feature_dtype':'F32','feature_shape':[1,6656],'tokens_key':'prompt_tokens','tokens_dtype':'I32','tokens_shape':[4],'prompt_tokens_sha256':hashlib.sha256(tokens).hexdigest()}
        run['actual_feature_writes']=[dict(image_id='a',feature_sha256=entry['tensor_sha256'])]
        (root/'encoder-run.json').write_text(json.dumps(run))
        descriptor={'schema_version':'beverage-feature-cache-v1','execution_policy':'separate-frozen-vision-v1','encoder_config_sha256':enc,'encoder_config_path':'encoder-config.json','encoder_run_path':'encoder-run.json','encoder_run_sha256':hashlib.sha256((root/'encoder-run.json').read_bytes()).hexdigest(),'source_manifest_sha256':'b'*64,'split_policy_sha256':'c'*64,'split':'train','outcome':'complete','started_utc':'2026-11-02T12:00:00Z','completed_utc':'2026-11-02T12:01:01Z','entries':[entry]}
        path=root/'feature-cache.json';path.write_text(json.dumps(descriptor))
        args={'rows':[{'image_id':'a','image_sha256':'a'*64,'split':'train'}],'split':'train','encoder_sha256':enc,'source_manifest_sha256':'b'*64,'split_policy_sha256':'c'*64}
        return path,descriptor,args

    def test_valid_tensor_cache_binds_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path,descriptor,args=self.fixture(Path(directory).resolve())
            self.assertEqual(cache.verify_cache(path,**args)['entries'][0]['image_id'],'a')

    def test_rebound_valid_tensor_cannot_disagree_with_preserved_encoder_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path,d,args=self.fixture(root)
            tensor=root/'sample.safetensors';data=bytearray(tensor.read_bytes())
            header_size=struct.unpack('<Q',data[:8])[0]
            data[8+header_size:12+header_size]=struct.pack('<f',1)
            tensor.write_bytes(data)
            d['entries'][0]['tensor_sha256']=hashlib.sha256(data).hexdigest()
            path.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'encoder.*writ|writ.*encoder'):
                cache.verify_cache(path,**args)

    def test_encoder_writes_require_exact_unique_successful_case_hashes(self):
        for invalid in (None,[],[dict(image_id='foreign',feature_sha256='a'*64)],
                        [dict(image_id='a',feature_sha256='a'*64)]*2):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve();path,d,args=self.fixture(root)
                run_path=root/'encoder-run.json';run=json.loads(run_path.read_text())
                run['actual_feature_writes']=invalid;run_path.write_text(json.dumps(run))
                d['encoder_run_sha256']=hashlib.sha256(run_path.read_bytes()).hexdigest()
                path.write_text(json.dumps(d))
                with self.assertRaisesRegex(ValueError,'encoder.*writ|writ.*encoder'):
                    cache.verify_cache(path,**args)

    def test_tampered_tensor_and_wrong_split_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path,d,args=self.fixture(root)
            (root/'sample.safetensors').write_bytes(b'wrong')
            with self.assertRaises(ValueError):cache.verify_cache(path,**args)
            path,d,args=self.fixture(root);d['entries'][0]['split']='test';path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):cache.verify_cache(path,**args)

    def test_escaping_paths_and_unbound_prompt_tokens_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path,d,args=self.fixture(root)
            d['entries'][0]['tensor_path']='../outside.safetensors';path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):cache.verify_cache(path,**args)
            path,d,args=self.fixture(root);d['entries'][0]['prompt_tokens_sha256']='f'*64;path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):cache.verify_cache(path,**args)

    def test_symlink_root_and_descriptor_ancestors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();real=root/'real';real.mkdir()
            path,d,args=self.fixture(real)
            link=root/'link';link.symlink_to(real,target_is_directory=True)
            with self.assertRaises(ValueError):cache.safe_path(link,'sample.safetensors')
            with self.assertRaises(ValueError):cache.verify_cache(link/'feature-cache.json',**args)

    def test_missing_case_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            path,d,args=self.fixture(Path(directory).resolve());args['rows'].append({'image_id':'missing','image_sha256':'e'*64,'split':'train'})
            with self.assertRaises(ValueError):cache.verify_cache(path,**args)

if __name__=='__main__':unittest.main()
