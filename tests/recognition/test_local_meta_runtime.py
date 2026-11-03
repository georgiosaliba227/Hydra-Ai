"""Real subprocess/resource boundary checks without loading model weights."""
import fcntl
import json
import os
from pathlib import Path
import sys
import subprocess
import time

import pytest


def test_child_has_no_provider_or_app_credentials_and_no_retry(tmp_path,monkeypatch):
    from backend.local_meta_runtime import run_bounded
    monkeypatch.setenv('HYDRA_META_GEORGIO_API_KEY','private-example')
    monkeypatch.setenv('HYDRA_API_TOKEN','private-session')
    output=tmp_path/'environment.json'
    run_bounded([sys.executable,'-c','import os,json,sys;open(sys.argv[1],"w").write(json.dumps(dict(os.environ)))',str(output)],timeout=5)
    env=json.loads(output.read_text())
    assert not any('KEY' in key or 'TOKEN' in key or key.startswith(('HYDRA','META','WONDER')) for key in env)
    attempts=tmp_path/'attempts'
    with pytest.raises(ValueError):
        run_bounded([sys.executable,'-c','import sys;open(sys.argv[1],"a").write("attempt");sys.exit(1)',str(attempts)],timeout=5)
    assert attempts.read_text()=='attempt'


def test_timeout_reaps_child_and_returns_no_private_output(tmp_path,monkeypatch):
    from backend.local_meta_runtime import run_bounded
    # Isolate the deadline from the macOS-only RSS sampler. On Ubuntu the
    # production sampler correctly fails closed before this timeout expires.
    monkeypatch.setattr('backend.local_meta_runtime.child_resident_bytes',lambda _: 0)
    pid=tmp_path/'pid'
    with pytest.raises(ValueError,match='local_runtime_timeout'):
        run_bounded([sys.executable,'-c','import os,time,sys;open(sys.argv[1],"w").write(str(os.getpid()));print("PRIVATE",flush=True);time.sleep(10)',str(pid)],timeout=.3)
    with pytest.raises(ProcessLookupError): os.kill(int(pid.read_text()),0)


def test_monitor_failure_reaps_live_child_without_retry(monkeypatch):
    from backend import local_meta_runtime as runtime
    children=[]
    popen=subprocess.Popen
    def track_child(*args,**kwargs):
        child=popen(*args,**kwargs)
        children.append(child)
        return child
    def unavailable(_):
        raise runtime.LocalProcessError('resident_measurement_unavailable')
    monkeypatch.setattr(runtime.subprocess,'Popen',track_child)
    monkeypatch.setattr(runtime,'child_resident_bytes',unavailable)
    with pytest.raises(ValueError,match='local_runtime_monitor_failed'):
        runtime.run_bounded([sys.executable,'-c','import time;time.sleep(10)'],timeout=5)
    assert len(children)==1
    assert children[0].poll() is not None
    with pytest.raises(ProcessLookupError): os.kill(children[0].pid,0)


def test_runtime_lock_covers_whole_multistage_request_and_releases_on_error(tmp_path):
    from backend.local_meta_runtime import request_lock
    path=tmp_path/'lock'
    with request_lock(path):
        with pytest.raises(ValueError,match='local_runtime_busy'):
            with request_lock(path): pass
    with pytest.raises(RuntimeError):
        with request_lock(path): raise RuntimeError('test')
    with request_lock(path): pass


def test_wrong_pinned_executable_is_rejected_before_any_run(tmp_path):
    from backend.local_meta_runtime import LocalMetaRuntime
    binary=tmp_path/'fake'
    binary.write_text('do not run')
    with pytest.raises(ValueError,match='pinned executable'):
        LocalMetaRuntime(binary=binary,model=tmp_path/'model',adapter=tmp_path/'adapter',
                         encoder=tmp_path/'encoder',ocr=binary,work_root=tmp_path/'work')


def test_decoder_command_binds_the_actual_encoded_cache_bytes(tmp_path):
    from backend.local_meta_runtime import native_cache_arguments
    descriptor=tmp_path/'feature-cache.json'
    descriptor.write_bytes(b'abc')
    args=native_cache_arguments(descriptor)
    assert args[args.index('--feature-cache')+1]==str(descriptor)
    assert args[args.index('--feature-cache-sha256')+1]=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'


def test_orphan_worker_keeps_request_locked_after_backend_death(tmp_path):
    from backend.local_meta_runtime import request_lock
    lock=tmp_path/'lock';pid=tmp_path/'worker-pid'
    worker='import os,time,sys;open(sys.argv[1],"w").write(str(os.getpid()));time.sleep(10)'
    parent='''from pathlib import Path
import sys
from backend.local_meta_runtime import request_lock,run_bounded
with request_lock(Path(sys.argv[1])):
 run_bounded([sys.executable,'-c',sys.argv[3],sys.argv[2]],timeout=15)
'''
    process=subprocess.Popen([sys.executable,'-c',parent,str(lock),str(pid),worker])
    worker_pid=None
    try:
        deadline=time.monotonic()+5
        while not pid.exists() and time.monotonic()<deadline: time.sleep(.02)
        assert pid.exists(),'Worker did not start'
        worker_pid=int(pid.read_text());process.kill();process.wait(timeout=2)
        with pytest.raises(ValueError,match='local_runtime_busy'):
            with request_lock(lock): pass
    finally:
        if process.poll() is None: process.kill();process.wait()
        if worker_pid is not None:
            try: os.kill(worker_pid,15)
            except ProcessLookupError: pass
