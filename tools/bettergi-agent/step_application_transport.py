"""Detached v1 transport adapter; production installation is deliberately unavailable.

This adapter validates software evidence and ACKs retained ledger dispositions.
It never commits native history and never derives a physical input/release claim.
"""
import hashlib
import math

import step_application_protocol as p
from step_application_ledger import ClientLedger

AVAILABLE = False
REQUEST_FIELDS = {'version','command','sessionId','ownerEpoch','goalVersion','requestId',
                  'frameId','observedAtMs','expiresAtMs','modelId','steps'}
EXTENSIONS = {'stepApplication','stepApplicationsAck'}


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

    def install(self, bridge):
        """A future native-owner integration must replace and separately qualify this barrier."""
        raise p.ProtocolError('step_applications_native_owner_unavailable')

    def propose(self, request, decision, steps, model_contract, token):
        """Retain exactly one original token and a detached wire extension before any write."""
        p.require(self._action is None,'transport_pending')
        raw=validate_submission(request)
        bound=p.make_binding(decision,request,steps,model_contract)
        self.ledger.propose(bound,token)
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
        if request.get('command')=='action' and self._action is not None and not write_attempted:
            request_id,token,_=self._action
            self.ledger.not_submitted(request_id,token);self._action=None
        else:self.ledger.uncertain('transport_outcome_unknown')

    def receive(self, request, response, *, observed_client_ns):
        """Validate the entire batch and linked terminals before ACK; never call a native commit."""
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
        except BaseException:
            self.ledger.uncertain('transport_invalid_response');raise


def parse_header(raw):
    """The active bridge uses the exact H02 duplicate/type/finite parser for the whole combined JSON header."""
    message=p.decode(raw,4*1024*1024)
    p.require(type(message) is dict,'header_object')
    return message
