"""Run the Meta-consent UI case with a loopback FAKE provider and generated image.
No Meta/GitHub notification requests, real credentials or persistent approvals.
Requires the existing development pytest/uvicorn environment; not production code.
"""
import argparse
import socket
import sys,os,tempfile,secrets,subprocess,time,hashlib,threading
from pathlib import Path


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',default='platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5')
    parser.add_argument('--derived-data',default='/tmp/hydra-guarded-live-ui-derived')
    parser.add_argument('--skip-simulator-diagnostics',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests/recognition'))
    os.environ['HYDRA_AI_MODE']='mock';os.environ['META_BILLABLE_REQUESTS_ENABLED']='false'
    from test_guarded_meta import evidence,price,FakeTransport,FakeNotifier,ACCOUNTS,future
    from backend.app import create_app
    from backend.meta_accounts import AccountLedger,FirstPermit
    from backend.meta_gateway import GuardedMetaGateway, GitHubNotifier
    from backend.meta_provider import OfficialMetaTransport
    from backend.meta_images import sanitized_jpeg
    import uvicorn
    # Defense against any accidental real transport path in this simulation process.
    def forbidden(*args,**kwargs): raise AssertionError('Real Meta forbidden in UI simulation')
    OfficialMetaTransport.generate=forbidden
    GitHubNotifier.deliver=forbidden
    with tempfile.TemporaryDirectory(prefix='hydra-live-simulation-') as folder:
        token=secrets.token_urlsafe(40); path=Path(folder)/'synthetic.sqlite3'
        ledger=AccountLedger(path);ledger.initialize_accounts();ledger.attest_account(evidence());ledger.record_price(price())
        app=create_app(path,token);app.state.recognition_mode='meta_live'
        class SimulatedRecognizer:
            def __init__(self): self.lock=threading.Lock();self.approved=False
            def analyze(self,payload):
                with self.lock:
                    if not self.approved:
                        digest=hashlib.sha256(sanitized_jpeg(payload)).hexdigest()
                        ledger.approve_first_test(FirstPermit(account_id=ACCOUNTS[0],image_sha256=digest,price_version='fixture-v1',developer_approvals=ACCOUNTS,spending_authority_reference='SYNTHETIC-NO-SPEND',account_owner_authorization_reference='SYNTHETIC-ACCOUNT-OWNER',image_owner_consent_reference='GENERATED-FIXTURE-ONLY',valid_until=future()))
                        self.approved=True
                return GuardedMetaGateway(ledger,ACCOUNTS[0],FakeTransport(),FakeNotifier()).analyze(payload)
        app.state.recognizer=SimulatedRecognizer()
        app.router.routes[:]=[route for route in app.router.routes if getattr(route,'path',None)!='/health']
        @app.get('/health')
        def health(): return {'status':'ok','ai_mode':'meta_live','billable_requests_enabled':False,'test_provider':'fake-no-network'}
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        try:
            for _ in range(50):
                if server.started:break
                time.sleep(.1)
            if not server.started:
                raise RuntimeError('Local fake-provider server did not start.')
            env=os.environ.copy();env['HYDRA_API_TOKEN']=token;env['HYDRA_E2E_BACKEND_URL']=f'http://127.0.0.1:{port}'
            result=subprocess.run([sys.executable,str(root/'scripts/run_ios_e2e.py'),'--destination',args.destination,'--derived-data',args.derived_data,'--live-simulation',*(['--skip-simulator-diagnostics'] if args.skip_simulator_diagnostics else [])],env=env)
            raise SystemExit(result.returncode)
        finally: server.should_exit=True;thread.join(timeout=5);listener.close()


if __name__ == "__main__":
    main()
