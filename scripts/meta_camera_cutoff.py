"""Private operator activation/status and one explicit camera verification.

No loops or retries. Activation appends a new policy; it never resets old rows.
Keys remain in memory after reading the owner's existing private environment.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import stat
from time import monotonic_ns

from backend.meta_camera_cutoff import (CutoffCameraLedger, CutoffCameraPolicy,
                                       CutoffCameraGateway, CutoffCameraTransport)
from backend.meta_camera_preparation import _private_jpeg
from backend.meta_observations import read_observation
from backend.recognition import AnalysisRequest
from scripts.meta_preflight import read_private_environment


def _private_output(path: Path):
    if (not path.is_absolute() or any(part.is_symlink() for part in (path,*path.parents))
            or path.exists()):
        raise ValueError('A new private absolute output path is required')
    parent=path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('Owned private output directory required')
    return os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)


def analyze_once(env_file: Path,database: str|Path,image_file: Path,output_file: Path) -> dict:
    environment=read_private_environment(env_file)
    if environment.get('HYDRA_META_ACCOUNT') != 'georgiosaliba227':
        raise ValueError('Existing Georgio backend configuration required')
    ledger=CutoffCameraLedger(database)
    transport=CutoffCameraTransport(environment.get('HYDRA_META_GEORGIO_API_KEY',''))
    ledger.verify_credential('georgiosaliba227',transport.credential_fingerprint)
    request=AnalysisRequest(image_base64=base64.b64encode(_private_jpeg(image_file)).decode(),
                            photo_consent=True,meta_photo_consent=True,mode='meta_live')
    try:
        descriptor=_private_output(output_file)
    except OSError:
        raise ValueError('Private result cannot be created') from None
    report={'policy_version':'georgio-camera-cutoff-v1','recognition':None,'provider_reply':None,'observation':None,'error':None}
    with ledger.transaction() as db:
        before={row[0] for row in db.execute('SELECT attempt_id FROM camera_cutoff_attempts')}
    started=monotonic_ns()
    try:
        result=CutoffCameraGateway(ledger,transport).analyze(request)
        report['recognition']=result.model_dump(mode='json')
        report['attempt_id']=result.recognition_id
    except Exception:
        report['error']='analysis_unavailable; no automatic retry was performed'
    finally:
        report['elapsed_ms']=(monotonic_ns()-started)//1_000_000
        if transport.last_reply is not None:
            report['provider_reply']={'status':transport.last_reply.status,'body':transport.last_reply.body}
        try:
            with ledger.transaction() as db:
                added={row[0] for row in db.execute('SELECT attempt_id FROM camera_cutoff_attempts')}-before
            if len(added)==1:
                report['attempt_id']=added.pop()
                report['observation']=read_observation(database,report['attempt_id'])
            report['cutoff_status']=ledger.cutoff_status()
        except Exception:
            report['ledger_status']='requires_operator_inspection; all reservations retained'
        with os.fdopen(descriptor,'w') as output:
            json.dump(report,output,indent=2,sort_keys=True,allow_nan=False)
            output.write('\n');output.flush();os.fsync(output.fileno())
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    subs=parser.add_subparsers(dest='command',required=True)
    activate=subs.add_parser('activate')
    activate.add_argument('--policy-file',required=True,type=Path)
    subs.add_parser('status')
    analyze=subs.add_parser('analyze')
    analyze.add_argument('--env-file',required=True,type=Path)
    analyze.add_argument('--image',required=True,type=Path)
    analyze.add_argument('--output',required=True,type=Path)
    analyze.add_argument('--execute-owner-authorized-analysis',required=True,action='store_true')
    args=parser.parse_args()
    try:
        ledger=CutoffCameraLedger(args.database)
        if args.command=='activate':
            info=args.policy_file.lstat()
            if (args.policy_file.is_symlink() or not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size>16384):
                raise ValueError
            report=ledger.activate(CutoffCameraPolicy.model_validate_json(args.policy_file.read_text()))
        elif args.command=='status':
            report=ledger.cutoff_status()
        else:
            result=analyze_once(args.env_file,args.database,args.image,args.output)
            report={key:result.get(key) for key in ('attempt_id','error','elapsed_ms','cutoff_status')}
        print(json.dumps(report,sort_keys=True))
    except Exception:
        raise SystemExit('Camera operation refused; no automatic retry. Inspect private ledger/output.') from None
    if args.command=='analyze' and report['error']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
