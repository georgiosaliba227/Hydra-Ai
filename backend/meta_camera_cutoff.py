"""Owner-authorized recurring camera admission; old financial history is immutable.

The cutoff constrains conservatively recorded exposure, not unknown provider
extras. No invoice, zero historical baseline, or released hold is manufactured.
"""
import hashlib
import json
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .meta_accounts import (AccountLedger, DispatchTicket, FINANCIAL_DDL,
                            _canonical_schema, stamp)
from .meta_budget import BudgetDenied
from .meta_policy import MODEL_CONTEXT
from .recognition import MODEL

POLICY_VERSION = 'georgio-camera-cutoff-v1'
ACCOUNT = 'georgiosaliba227'
CUTOFF_OUTPUT_LIMIT = 1024
CUTOFF_INPUT_LIMIT = MODEL_CONTEXT - CUTOFF_OUTPUT_LIMIT
REFERENCE_PRICE = {
    'version': 'muse-spark-1.3-standard-20261101-cutoff', 'model': MODEL,
    'source': 'https://dev.meta.ai/docs/pricing-rate-limits',
    'input_micro_per_million': 1250000, 'cached_micro_per_million': 150000,
    'output_micro_per_million': 4250000,
}
SCHEMA = {
    'camera_cutoff_policy': 'CREATE TABLE camera_cutoff_policy(id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL)',
    'camera_cutoff_attempts': 'CREATE TABLE camera_cutoff_attempts(attempt_id TEXT PRIMARY KEY, policy_sha256 TEXT NOT NULL, image_sha256 TEXT NOT NULL)',
}


def token_cost(inputs: int, outputs: int, cached: int = 0) -> int:
    return ((inputs-cached)*1250000 + cached*150000 + outputs*4250000 + 999999)//1000000


class CutoffCameraPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal['georgio-camera-cutoff-v1'] = POLICY_VERSION
    account_id: Literal['georgiosaliba227'] = ACCOUNT
    key_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    cutoff_micro_usd: Literal[120000000] = 120000000
    external_allocation_hold_micro_usd: Literal[85000000] = 85000000
    account_gross_floor_micro_usd: StrictInt = Field(ge=0,le=9_000_000_000_000_000)
    owner_authorization_reference: str = Field(min_length=1,max_length=1000)
    price_reference: str = Field(min_length=1,max_length=500)
    residual_provider_charge_risk_accepted: Literal[True]

    @field_validator('residual_provider_charge_risk_accepted',mode='before')
    @classmethod
    def explicit_risk(cls,value):
        if value is not True:
            raise ValueError('Explicit owner acceptance required')
        return True

    @field_validator('owner_authorization_reference','price_reference')
    @classmethod
    def meaningful(cls,value):
        if not value.strip():
            raise ValueError('Meaningful references required')
        return value


class CutoffCameraLedger(AccountLedger):
    """Only additive camera policy/attempts; legacy freeze and spent flags survive."""

    @staticmethod
    def _schema(db, *, allow_absent=False):
        objects=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        for name,ddl in FINANCIAL_DDL.items():
            if _canonical_schema(objects.get(name,'')) != _canonical_schema(ddl):
                raise BudgetDenied('Existing authoritative financial schema required')
        for name,ddl in SCHEMA.items():
            if name not in objects and allow_absent:
                continue
            if _canonical_schema(objects.get(name,'')) != _canonical_schema(ddl):
                raise BudgetDenied('Cutoff policy schema unavailable or inconsistent')

    def activate(self, policy: CutoffCameraPolicy) -> dict:
        self.verify_storage()
        policy=CutoffCameraPolicy.model_validate(policy.model_dump())
        raw=policy.model_dump_json(); digest=hashlib.sha256(raw.encode()).hexdigest()
        with self.transaction() as db:
            self._schema(db,allow_absent=True)
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise BudgetDenied('Ledger integrity check failed')
            account=db.execute('SELECT evidence FROM live_accounts WHERE account_id=?',(ACCOUNT,)).fetchone()
            if not account or json.loads(account[0]).get('key_sha256') != policy.key_sha256:
                raise BudgetDenied('Policy does not match existing verified account/key')
            for ddl in SCHEMA.values():
                db.execute(ddl.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
            existing=db.execute('SELECT policy,sha256 FROM camera_cutoff_policy WHERE id=1').fetchone()
            if existing:
                if existing != (raw,digest):
                    raise BudgetDenied('Existing cutoff authorization is immutable')
            else:
                db.execute('INSERT INTO camera_cutoff_policy VALUES(1,?,?,?)',(raw,digest,stamp()))
                self.event(db,ACCOUNT,'camera_cutoff_policy_activated',raw)
            self._policy(db,ACCOUNT)
        return self.cutoff_status()

    def _policy(self, db, account):
        self._schema(db)
        if account != ACCOUNT:
            raise BudgetDenied('Cutoff camera authorization is Georgio-only')
        row=db.execute('SELECT policy,sha256 FROM camera_cutoff_policy WHERE id=1').fetchone()
        try:
            policy=CutoffCameraPolicy.model_validate_json(row[0])
            if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
                raise ValueError
            prior=db.execute('SELECT evidence,anchor_gross FROM live_accounts WHERE account_id=?',(ACCOUNT,)).fetchone()
            evidence=json.loads(prior[0])
            if evidence['key_sha256'] != policy.key_sha256 or evidence['account_id'] != ACCOUNT:
                raise ValueError
            for amount in (prior[1],evidence['gross_micro_usd']):
                if type(amount) is not int or amount < 0:
                    raise ValueError
        except (ValueError,TypeError,KeyError,IndexError):
            raise BudgetDenied('Cutoff policy or account binding invalid') from None
        return policy

    @staticmethod
    def _exposure(db, policy):
        row=db.execute('SELECT anchor_gross,evidence FROM live_accounts WHERE account_id=?',(ACCOUNT,)).fetchone()
        floor=max(row[0],json.loads(row[1])['gross_micro_usd'],policy.account_gross_floor_micro_usd)
        held=0
        for reserved,actual in db.execute('SELECT reserved,actual FROM live_attempts WHERE account_id=?',(ACCOUNT,)):
            if type(reserved) is not int or reserved < 0 or (actual is not None and (type(actual) is not int or actual < 0)):
                raise BudgetDenied('Invalid recorded exposure')
            held += max(reserved,actual if actual is not None else 0)
        return floor + policy.external_allocation_hold_micro_usd + held

    def cutoff_status(self):
        self.verify_storage()
        with self.transaction() as db:
            policy=self._policy(db,ACCOUNT)
            exposure=self._exposure(db,policy)
            return {'policy_version':POLICY_VERSION,'account_id':ACCOUNT,
                    'exposure_micro_usd':exposure,'cutoff_micro_usd':policy.cutoff_micro_usd,
                    'external_allocation_hold_micro_usd':policy.external_allocation_hold_micro_usd,
                    'token_reservation_micro_usd':token_cost(CUTOFF_INPUT_LIMIT,CUTOFF_OUTPUT_LIMIT),
                    'invoice_finality_required':False,'request_count_limit':None,
                    'provider_total_charge_bound_micro_usd':None}

    def verify_credential(self, account, fingerprint):
        self.verify_storage()
        with self.transaction() as db:
            if self._policy(db,account).key_sha256 != fingerprint:
                raise BudgetDenied('Credential differs from verified account')

    def verify_purpose(self, account, purpose):
        self.verify_storage()
        with self.transaction() as db:
            self._policy(db,account)
            if purpose != 'camera':
                raise BudgetDenied('Camera authorization cannot enable another feature')

    def quote(self, account, input_bound):
        self.verify_storage()
        if type(input_bound) is not int or input_bound != CUTOFF_INPUT_LIMIT:
            raise BudgetDenied('Full reviewed model-context reservation required')
        with self.transaction() as db:
            self._policy(db,account)
        return dict(REFERENCE_PRICE),token_cost(input_bound,CUTOFF_OUTPUT_LIMIT)

    def reserve_first(self, account, image_hash, input_bound):
        _,maximum=self.quote(account,input_bound)
        if not isinstance(image_hash,str) or not re.fullmatch(r'[a-f0-9]{64}',image_hash):
            raise BudgetDenied('Normalized image hash required')
        attempt=str(uuid4())
        with self.transaction() as db:
            policy=self._policy(db,account)
            if db.execute("SELECT 1 FROM live_attempts WHERE state IN ('reserved','dispatched','sending',"
                          "'experiment_reserved','experiment_dispatched','experiment_sending')").fetchone():
                raise BudgetDenied('Another request is in flight')
            if self._exposure(db,policy)+maximum >= policy.cutoff_micro_usd:
                raise BudgetDenied('Account operational cutoff reached')
            digest=db.execute('SELECT sha256 FROM camera_cutoff_policy WHERE id=1').fetchone()[0]
            db.execute('INSERT INTO live_attempts(id,account_id,price,reserved,state,created_at,input_bound) VALUES(?,?,?,?,?,?,?)',
                       (attempt,account,json.dumps(REFERENCE_PRICE,sort_keys=True),maximum,'reserved',stamp(),input_bound))
            db.execute('INSERT INTO camera_cutoff_attempts VALUES(?,?,?)',(attempt,digest,image_hash))
            self.event(db,account,'camera_cutoff_reserved',attempt)
        return attempt

    def _attempt(self,db,attempt):
        policy=self._policy(db,ACCOUNT)
        row=db.execute('SELECT a.account_id,a.state,a.ticket_nonce,a.payload_sha256,a.input_bound,c.policy_sha256 '
                       'FROM live_attempts a JOIN camera_cutoff_attempts c ON a.id=c.attempt_id WHERE a.id=?',(attempt,)).fetchone()
        digest=db.execute('SELECT sha256 FROM camera_cutoff_policy WHERE id=1').fetchone()[0]
        if not row or row[0] != ACCOUNT or row[5] != digest or row[4] != CUTOFF_INPUT_LIMIT:
            raise BudgetDenied('Attempt is outside this camera policy')
        return policy,row

    def mark_dispatched(self,attempt,payload_sha256):
        self.verify_storage()
        if not isinstance(payload_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',payload_sha256):
            raise BudgetDenied('Exact payload digest required')
        nonce=str(uuid4())
        with self.transaction() as db:
            policy,row=self._attempt(db,attempt)
            if row[1] != 'reserved' or self._exposure(db,policy) >= policy.cutoff_micro_usd:
                raise BudgetDenied('Attempt cannot dispatch')
            db.execute("UPDATE live_attempts SET state='dispatched',dispatched_at=?,payload_sha256=?,ticket_nonce=? WHERE id=?",(stamp(),payload_sha256,nonce,attempt))
            self.event(db,ACCOUNT,'dispatched',attempt)
        return DispatchTicket(self,attempt,nonce)

    def claim_send(self,attempt,nonce,payload_sha256,input_bound,credential_fingerprint):
        self.verify_storage()
        with self.transaction() as db:
            policy,row=self._attempt(db,attempt)
            if (row[1:4] != ('dispatched',nonce,payload_sha256)
                    or type(input_bound) is not int or input_bound != row[4]
                    or credential_fingerprint != policy.key_sha256
                    or self._exposure(db,policy) >= policy.cutoff_micro_usd):
                raise BudgetDenied('No matching one-use network ticket below cutoff')
            db.execute("UPDATE live_attempts SET state='sending',ticket_nonce=NULL WHERE id=?",(attempt,))
            self.event(db,ACCOUNT,'network_send_claimed',attempt)

    def quarantine(self,attempt):
        self.verify_storage()
        with self.transaction() as db:
            self._attempt(db,attempt)
            db.execute("UPDATE live_attempts SET state='unresolved',ticket_nonce=NULL WHERE id=? AND actual IS NULL",(attempt,))
            self.event(db,ACCOUNT,'camera_cutoff_hold_retained',attempt)

    def settle_provider_reply(self,attempt,reply):
        self.verify_storage()
        blocked=False
        with self.transaction() as db:
            _,row=self._attempt(db,attempt)
            if row[1] != 'sending':
                raise BudgetDenied('No unsettled network send')
            body=reply.body
            try:
                identifier=body.get('id')
                if body.get('model') == MODEL and isinstance(identifier,str) and re.fullmatch(r'resp_[A-Za-z0-9_-]{1,180}',identifier):
                    db.execute('UPDATE live_attempts SET provider_id=? WHERE id=?',(identifier,attempt))
                else:
                    raise ValueError
                usage=body['usage'];inputs=usage['input_tokens'];outputs=usage['output_tokens']
                cached=usage['input_tokens_details']['cached_tokens'];total=usage['total_tokens']
                if (any(type(x) is not int or x<0 for x in (inputs,outputs,cached,total))
                        or cached>inputs or total != inputs+outputs
                        or db.execute('SELECT 1 FROM live_attempts WHERE account_id=? AND provider_id=? AND id!=?',(ACCOUNT,identifier,attempt)).fetchone()):
                    raise ValueError
                cost=token_cost(inputs,outputs,cached)
                raw=json.dumps({'input_tokens':inputs,'output_tokens':outputs,'cached_tokens':cached,'total_tokens':total},sort_keys=True)
                db.execute("UPDATE live_attempts SET usage=?,reserved=MAX(reserved,?),state='billing_pending' WHERE id=?",(raw,cost,attempt))
                self.event(db,ACCOUNT,'camera_cutoff_usage_recorded',json.dumps({'attempt_id':attempt,'token_cost_micro_usd':cost,'provider_total_charge_micro_usd':None},sort_keys=True))
                if inputs>CUTOFF_INPUT_LIMIT or outputs>CUTOFF_OUTPUT_LIMIT:
                    raise ValueError
            except (ValueError,KeyError,TypeError,AttributeError):
                db.execute("UPDATE live_attempts SET state='unresolved' WHERE id=?",(attempt,))
                self.event(db,ACCOUNT,'camera_cutoff_usage_unverified',attempt)
                blocked=True
        if blocked:
            raise BudgetDenied('Provider usage unverified or exceeded model bound')


# Same fixed-origin HTTP implementation, with the separately accounted output
# budget. No transport retries, endpoint override, tools or account fallback.
from .meta_provider import OfficialMetaTransport, request_payload
from .meta_gateway import GuardedMetaGateway
from .recognition import AnalysisRequest


class CutoffCameraTransport(OfficialMetaTransport):
    def input_bound(self,payload):
        return CUTOFF_INPUT_LIMIT

    def validate_payload(self,payload):
        image_url=payload['input'][0]['content'][1]['image_url']
        prefix='data:image/jpeg;base64,'
        if not image_url.startswith(prefix):
            raise ValueError
        image=AnalysisRequest(image_base64=image_url[len(prefix):],photo_consent=True,
                              mode='meta_live',meta_photo_consent=True)
        if payload != request_payload(image,output_limit=CUTOFF_OUTPUT_LIMIT):
            raise ValueError


class CutoffCameraGateway(GuardedMetaGateway):
    def __init__(self,ledger: CutoffCameraLedger,transport: CutoffCameraTransport):
        self.ledger,self.account,self.transport=ledger,ACCOUNT,transport

    def build_payload(self,image):
        return request_payload(image,output_limit=CUTOFF_OUTPUT_LIMIT)

    def deliver_pending_notices(self):
        # Owner replaced the $75/$100 financial gates for this path. Existing
        # notices are untouched; inference sends no GitHub messages.
        return None
