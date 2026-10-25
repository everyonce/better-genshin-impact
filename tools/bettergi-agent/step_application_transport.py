"""Detached v1 transport adapter; production installation is deliberately unavailable.

This adapter validates software evidence and ACKs retained ledger dispositions.
It never commits native history and never derives a physical input/release claim.
"""
import hashlib
import math
from dataclasses import dataclass

import step_application_protocol as p
from step_application_ledger import ClientLedger

AVAILABLE = False
REQUEST_FIELDS = {'version','command','sessionId','ownerEpoch','goalVersion','requestId',
                  'frameId','observedAtMs','expiresAtMs','modelId','steps'}
EXTENSIONS = {'stepApplication','stepApplicationsAck'}


@dataclass(frozen=True, eq=False)
class SubmissionDisposition:
    """Exact retained local token disposition; admission never means model publication."""
    intake: object
    request_id: str
    token: object
    status: str
    write_attempted: object
    observed_client_ns: object = None
    registered: bool = True


def validate_submission(request):
    """Reject extra fields and typed normalization before hashing the actual action."""
    p.require(type(request) is dict and set(request) in (REQUEST_FIELDS, REQUEST_FIELDS|{'startBeforeMs'}), 'submission_fields')
    p.require(type(request['version']) is int and request['version']==1 and request['command']=='action','submission_command')
    for key in ('sessionId','ownerEpoch','requestId','modelId'):p.text(request[key])
    for key in ('goalVersion','frameId'):p.integer(request[key])
    for key in ('observedAtMs','expiresAtMs','startBeforeMs'):
        if key in request:p.require(type(request[key]) in (int,float) and math.isfinite(request[key]),'submission_time')
    p.require(type(request['steps']) is list and len(request['steps'])==1,'single_interval')
    p.step(request['steps'][0])
    p.require(not set(request['steps'][0]['keys']) & {'SHIFT','CONTROL','ESC'},'alias_authority')
    return p.canonical(request,16384)


def validate_envelope(request):
    """Check the versioned canonical byte contract without modifying the reviewed H02 binding."""
    p.require(type(request) is dict and 'stepApplication' in request,'submission_extension')
    ext=request['stepApplication'];p.fields(ext,('version','submissionJson','binding'))
    p.require(type(ext['version']) is int and ext['version']==1,'extension_version')
    p.require(type(ext['submissionJson']) is str and ext['submissionJson'].isascii(),'submission_ascii')
    raw=ext['submissionJson'].encode('ascii');original=p.decode(raw,16384)
    p.require(validate_submission(original)==raw,'submission_not_canonical')
    actual={k:v for k,v in request.items() if k not in EXTENSIONS}
    p.require(validate_submission(actual)==raw,'submission_wire_mismatch')
    p.require(ext['binding']['submissionSha256']==hashlib.sha256(raw).hexdigest(),'submission_digest')
    return raw


class StepApplicationIntake:
    """A confirmed detached channel, called only inside the existing Bridge serialization lock.

    Construction is an inert/test or future reviewed integration seam. No CLI or
    production factory installs it, and install() remains unconditionally blocked.
    """
    def __init__(self, configuration, confirmation):
        """Require exact server confirmation; no invented R45 capability fallback."""
        self.config=p.decode(p.configuration(configuration),4096)
        p.require(not set(self.config['allowedKeys']) & {'SHIFT','CONTROL','ESC'},'alias_authority')
        self.ledger=ClientLedger(self.config,confirmation)
        self._action=None
        self._ack=0
        self._terminal_ack=[]
        self._dispositions = {}

    def install(self, bridge):
        """A future native-owner integration must replace and separately qualify this barrier."""
        raise p.ProtocolError('step_applications_native_owner_unavailable')

    def propose(self, request, decision, steps, model_contract, token):
        """Retain exactly one original token and a detached wire extension before any write."""
        p.require(self._action is None,'transport_pending')
        raw=validate_submission(request)
        bound=p.make_binding(decision,request,steps,model_contract)
        self.ledger.propose(bound,token)
        self._dispositions[request['requestId']] = SubmissionDisposition(
            self, request['requestId'], token, 'pending', None)
        result=p.decode(raw,16384)
        result['stepApplication']=dict(version=1,submissionJson=raw.decode('ascii'),binding=p.decode(bound,3072))
        p.canonical(result,65536)
        self._action=(request['requestId'],token,p.canonical(result,65536))
        return p.decode(self._action[2],65536)

    def prepare(self, request):
        """Add a versioned ACK only for already validated retained records/terminal dispositions."""
        p.require(type(request) is dict and request.get('sessionId')==self.config['sessionId']
                  and request.get('ownerEpoch')==self.config['ownerEpoch'],'transport_lease')
        p.require(type(request.get('version')) is int and request['version']==1
                  and type(request.get('goalVersion')) is int and request['goalVersion']==1,'transport_version_goal')
        command=request.get('command')
        p.require(command in ('action','frame','status','release','stop'),'transport_command')
        result=p.decode(p.canonical(request,65536),65536)
        p.require('stepApplicationsAck' not in result,'caller_ack')
        if self.ledger.quarantined:
            p.require(command in ('release','stop'),'transport_quarantined')
            return result
        if command=='action':
            p.require(self._action is not None and p.canonical(result,65536)==self._action[2],'transport_action_binding')
            validate_envelope(result)
        else:
            p.fields(result,('version','command','sessionId','ownerEpoch','goalVersion'))
        result['stepApplicationsAck']=dict(version=1,channelId=self.config['channelId'],through=self._ack,
                                           terminalRequestIds=list(self._terminal_ack))
        p.canonical(result['stepApplicationsAck'],4096)
        p.canonical(result,65536)
        return result

    def failed(self, request, *, write_attempted):
        """Only an explicit pre-write failure is known not submitted; a failed write is ambiguous."""
        p.require(type(write_attempted) is bool, 'write_attempted_boolean')
        if request.get('command')=='action' and self._action is not None and not write_attempted:
            request_id,token,_=self._action
            self.ledger.not_submitted(request_id,token);self._action=None
            self._dispositions[request_id] = SubmissionDisposition(self, request_id, token, 'known_not_submitted', False)
        else:
            if request.get('command') == 'action' and self._action is not None:
                request_id, token, _ = self._action
                previous = self._dispositions.get(request_id)
                observed = previous.observed_client_ns if previous is not None and previous.token is token else None
                self._dispositions[request_id] = SubmissionDisposition(self, request_id, token, 'unknown', write_attempted, observed)
            self.ledger.uncertain('transport_outcome_unknown')

    def receive(self, request, response, *, observed_client_ns):
        """Validate the entire batch and linked terminals before ACK; never call a native commit."""
        pending_action = self._action
        if self.ledger.quarantined:
            p.require(request['command'] in ('release','stop'),'transport_quarantined')
            return  # Cleanup can proceed; these unvalidated bytes grant no ACK or authority.
        try:
            if request['command']=='action':
                p.require(self._action is not None and response.get('requestId')==self._action[0]
                          and response.get('type') in ('accepted','rejected'),'transport_admission')
                request_id,token,_=self._action
                self.ledger.admission(request_id,token,accepted=response['type']=='accepted');self._action=None
            p.require(type(response.get('stepApplications')) is dict
                      and type(response.get('stepApplicationTerminals')) is list,'transport_extensions')
            terminals=response['stepApplicationTerminals']
            ack=self.ledger.ingest(p.canonical(response['stepApplications']),[p.canonical(t,4096) for t in terminals],
                                   observed_client_ns=observed_client_ns)
            # No publication callback occurs here. The ACK only frees facts already retained by this ledger.
            self._ack=ack;self._terminal_ack=[t['binding']['requestId'] for t in terminals]
            if request['command'] == 'action' and pending_action is not None:
                request_id, token, _ = pending_action
                self._dispositions[request_id] = SubmissionDisposition(self, request_id, token,
                    response['type'] if not self.ledger.quarantined else 'unknown', True, observed_client_ns)
        except BaseException:
            if request['command'] == 'action' and pending_action is not None:
                request_id, token, _ = pending_action
                observed = observed_client_ns if type(observed_client_ns) is int and observed_client_ns >= 0 else None
                self._dispositions[request_id] = SubmissionDisposition(self, request_id, token, 'unknown', True, observed)
            self.ledger.uncertain('transport_invalid_response');raise

    def submission_disposition(self, request_id, token):
        """Return the exact immutable proof; whole-batch uncertainty overrides intermediate admission."""
        proof = self._dispositions[request_id]
        p.require(proof.token is token and proof.intake is self, 'disposition_token')
        if self.ledger.quarantined and proof.status != 'unknown':
            proof = SubmissionDisposition(self, request_id, token, 'unknown', proof.write_attempted,
                                          proof.observed_client_ns, proof.registered)
            self._dispositions[request_id] = proof
        return proof

    def verify_disposition(self, proof, token, request_id):
        """A copied or stale proof cannot authorize a native rollback or admission."""
        p.require(type(proof) is SubmissionDisposition and proof is self.submission_disposition(request_id, token)
                  and proof.token is token, 'disposition_not_current')
        return self.ledger.submission_status(request_id, token)

    def abort_prewrite_registration(self, request_id, token):
        """Coordinator-only local construction failure before any Bridge invocation; never a write result."""
        p.require(self._action is None or self._action[0] == request_id and self._action[1] is token,
                  'abort_foreign_action')
        row = self.ledger.submission_status(request_id, token)
        if row is not None:
            proof = self.submission_disposition(request_id, token)
            p.require(proof.status == 'pending' and proof.write_attempted is None, 'abort_not_unwritten')
            self.ledger.not_submitted(request_id, token)
        else:
            p.require(request_id not in self._dispositions and len(self._dispositions) < p.OUTBOX_RECORDS,
                      'abort_registration_or_capacity')
        self._action = None
        proof = SubmissionDisposition(self, request_id, token, 'known_not_submitted', False, registered=row is not None)
        self._dispositions[request_id] = proof
        return proof

    def disposition_metadata(self):
        """At most 32 detached rows; opaque token and tensor owners never enter JSON."""
        rows = [dict(requestId=v.request_id, status=v.status, writeAttempted=v.write_attempted,
                     observedClientNs=v.observed_client_ns) for v in self._dispositions.values()]
        p.require(len(rows) <= p.OUTBOX_RECORDS, 'disposition_capacity')
        return p.canonical(rows, 16384)


def parse_header(raw):
    """The active bridge uses the exact H02 duplicate/type/finite parser for the whole combined JSON header."""
    message=p.decode(raw,4*1024*1024)
    p.require(type(message) is dict,'header_object')
    return message
