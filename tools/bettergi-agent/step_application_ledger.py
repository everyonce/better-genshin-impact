"""Inert producer outbox and client ledger for the proposed step-application v1.

No input dispatch, server endpoint, C# producer, model import or native owner is
installed. Locks cover only detached ledger state; callbacks run outside locks.
This prototype bounds a negotiated channel to 32 attempts, then requires closure;
it deliberately supplies no channel recycling or crash-recovery adoption API.
"""
import hashlib
import json
import threading

import step_application_protocol as p


class Outbox:
    """Reserve immutable capacity before dispatch; explicit opt-in is initially absent."""
    def __init__(self):
        self._lock=threading.RLock()
        self._config=None
        self._rows={}
        self._tickets={}
        self._requests=set()
        self._ack=0
        self._next=1
        self._lost=False
        self._closed=False
        self._last_ticks=0
        self._tracked=None

    def enable(self,config,initial_tracked,*,idle):
        """Caller must authenticate the request; returned bytes are the exact enable reply."""
        with self._lock:
            p.require(idle is True and self._config is None and not self._closed,'enable_idle_once')
            raw=p.configuration(config);p.tracked(initial_tracked)
            p.require(initial_tracked['complete'],'unknown_initial_state')
            self._config=raw;self._tracked=p.canonical(initial_tracked);self._last_ticks=config['sessionOriginTicks']
            return p.canonical(dict(configuration=p.decode(raw),initialTracked=p.decode(self._tracked),limits=p.LIMITS))

    def reserve(self,binding_bytes):
        """A ticket reserves a full 8 KiB slot before any caller could dispatch input."""
        with self._lock:
            p.require(self._config is not None and not self._closed and not self._lost,'channel_inactive')
            p.require(not self._tickets,'dispatch_already_reserved')
            if len(self._rows)>=p.OUTBOX_RECORDS or self._next>p.OUTBOX_RECORDS:
                self._lost=True;raise p.ProtocolError('bounded_channel_exhausted')
            config=p.decode(self._config);value=p.decode(binding_bytes,3072);p.binding(value,config)
            p.require(value['requestId'] not in self._requests,'request_reuse')
            before=p.decode(self._tracked)
            p.require(before['generation']<p.MAX_INT,'state_counter_exhausted')
            p.require(p.reservation_byte_bound(value,config,before,self._next)<=p.RECORD_BYTES,'reservation_byte_budget')
            ticket=object();sequence=self._next;self._next+=1
            self._requests.add(value['requestId'])
            self._tickets[ticket]=(sequence,p.canonical(value),self._tracked)
            return ticket

    def finish(self,ticket,evidence):
        """Freeze actual observed call evidence; failure never retries or removes reservation."""
        with self._lock:
            p.require(not self._lost and ticket in self._tickets,'reservation')
            sequence,bound,tracked=self._tickets[ticket];config=p.decode(self._config)
            try:
                # Detach caller-owned data before either validation or retention.
                row=p.decode(p.canonical(evidence,p.RECORD_BYTES))
                row.update(version=p.VERSION,sequence=sequence,channelId=config['channelId'],backendEpoch=config['backendEpoch'],
                    binding=p.decode(bound),clock={k:config[k] for k in ('clockKind','sessionOriginTicks','clockFrequency')})
                p.require(p.canonical(row['trackedBefore'])==tracked,'reservation_state_changed')
                p.require(row['dispatchStartedTicks']>=self._last_ticks,'producer_clock_regressed')
                raw=p.validate_record(row,config)
                self._rows[sequence]=raw
                self._tracked=p.canonical(row['trackedAfter'])
                self._last_ticks=row['publicationTicks']
                del self._tickets[ticket]
                if row['outcome']!='complete_returned':self._lost=True
                return raw
            except BaseException:
                self._lost=True
                raise

    def publication_failed(self,ticket):
        """An instrumentation/publication failure retains the unresolved slot and poisons authority."""
        with self._lock:
            p.require(ticket in self._tickets,'reservation')
            self._lost=True

    def batch(self):
        """Retransmit immutable rows without draining; unpublished reservations stay explicit."""
        with self._lock:
            p.require(self._config is not None,'not_negotiated')
            config=p.decode(self._config);seq=sorted(self._rows)
            return p.canonical(dict(version=p.VERSION,channelId=config['channelId'],acknowledgedThrough=self._ack,
                nextReservedSequence=self._next,authorityLost=self._lost,unpublished=len(self._tickets),
                records=[p.decode(self._rows[s]) for s in seq[:p.BATCH_RECORDS]]))

    def combine_reply(self,legacy_bytes):
        """Opted-in JSON extension shares the existing 4 MiB header; binary RGB stays separate."""
        with self._lock:
            if self._config is None or self._closed:return legacy_bytes
            try:
                value=p.decode(legacy_bytes,4*1024*1024)
                p.require(type(value) is dict and 'stepApplications' not in value,'reply_extension_collision')
                value['stepApplications']=p.decode(self.batch())
                return p.canonical(value,4*1024*1024)
            except BaseException:
                self._lost=True
                raise

    def acknowledge(self,through):
        """Cumulative ACK releases only an existing contiguous prefix; it is not model publication."""
        with self._lock:
            p.integer(through,self._ack,self._next-1)
            p.require(all(n in self._rows for n in range(self._ack+1,through+1)),'ack_gap')
            for n in range(self._ack+1,through+1):del self._rows[n]
            self._ack=through

    def disable(self,*,idle,terminal_reconciled):
        """Disable cannot erase unacknowledged or unresolved state or permit re-enabling this object."""
        with self._lock:
            p.require(idle is True and terminal_reconciled is True and not self._rows and not self._tickets
                and not self._lost,'disable_unresolved')
            self._closed=True


class ClientLedger:
    """Validate complete response batches before a consume-once fake/native publication seam."""
    def __init__(self,expected_config,enable_reply):
        self._lock=threading.RLock()
        self._config=p.configuration(expected_config)
        reply=p.decode(enable_reply,8192);p.fields(reply,('configuration','initialTracked','limits'))
        p.require(p.canonical(reply['configuration'])==self._config,'enable_not_confirmed')
        p.require(p.canonical(reply['limits'])==p.canonical(p.LIMITS),'negotiated_limits')
        p.tracked(reply['initialTracked']);p.require(reply['initialTracked']['complete'],'unknown_initial_state')
        self._tracked=p.canonical(reply['initialTracked'])
        self._proposals={}
        self._records={}
        self._terminals={}
        self._ack=0
        self._server_ack=0
        self._next_reserved=1
        self._observed=0
        self._ticks=expected_config['sessionOriginTicks']
        self._quarantine=None
        self._publishing=False
        self._generation=0
        self._snapshot_cutoff=0
        self._decision_scope=None

    def _ready(self):
        """Quarantine and in-progress publication forbid dependent transitions."""
        p.require(self._quarantine is None and not self._publishing,'ledger_quarantined_or_publishing')

    def _poison(self,label,raw=b''):
        """Keep one bounded immutable failure reference without erasing prior publication."""
        if self._quarantine is None:self._quarantine=(str(label)[:128],hashlib.sha256(raw).hexdigest())

    def propose(self,binding_bytes,token):
        """Retain an opaque local identity; submitted wire/model transformation is already bound."""
        with self._lock:
            self._ready();p.require(token is not None,'private_token')
            value=p.decode(binding_bytes,3072);p.binding(value,p.decode(self._config))
            scope=p.canonical(dict(identity={k:v for k,v in value['identity'].items() if k!='frameId'},model=value['model']))
            if self._decision_scope is not None and scope!=self._decision_scope:
                self._poison('decision_or_model_epoch_changed');raise p.ProtocolError('decision_or_model_epoch_changed')
            self._decision_scope=scope
            p.require(len(self._proposals)<p.OUTBOX_RECORDS,'channel_capacity')
            active=[v for v in self._proposals.values() if v['phase']!='not_submitted'
                and not(v['terminal']=='completed' and v['publishedGeneration'] is not None)]
            p.require(not active or (len(active)==1 and active[0]['publishedGeneration'] is not None),'native_single_pending')
            request=value['requestId'];p.require(request not in self._proposals,'request_reuse')
            self._proposals[request]=dict(binding=p.canonical(value),token=token,phase='proposed',
                sequence=None,terminal=None,attempted=False,publishedGeneration=None)

    def admission(self,request,token,*,accepted):
        """Only explicit known admission/rejection is representable; ambiguous write quarantines."""
        with self._lock:
            self._ready();row=self._proposals[request]
            p.require(token is row['token'] and row['phase']=='proposed' and type(accepted) is bool,'admission')
            row['phase']='admitted' if accepted else 'not_submitted'

    def not_submitted(self,request,token):
        """Record local no-write disposition; actual native rollback is outside this prototype."""
        self.admission(request,token,accepted=False)

    def uncertain(self,reason):
        """Unknown transport/identity outcomes never fabricate no-op or release evidence."""
        with self._lock:self._poison(reason)

    def ingest(self,batch_bytes,terminal_bytes,*,observed_client_ns):
        """Stage all records and terminals before applying anything; no callback is invoked here."""
        with self._lock:
            self._ready()
            try:
                p.integer(observed_client_ns,max(self._observed,self._snapshot_cutoff))
                value=p.decode(batch_bytes);config=p.decode(self._config)
                p.fields(value,('version','channelId','acknowledgedThrough','nextReservedSequence','authorityLost','unpublished','records'))
                p.require(type(value['version']) is int and value['version']==p.VERSION
                    and value['channelId']==config['channelId'],'batch_channel')
                p.integer(value['acknowledgedThrough'],self._server_ack,self._ack)
                p.integer(value['nextReservedSequence'],self._next_reserved,p.OUTBOX_RECORDS+1)
                p.integer(value['unpublished'],0,1);p.require(type(value['authorityLost']) is bool,'loss_flag')
                rows=value['records'];p.require(type(rows) is list and len(rows)<=p.BATCH_RECORDS,'batch_count')
                # The producer returns its complete first window after the server ACK.
                # Its only unpublished reservation is the newest sequence.
                finished=value['nextReservedSequence']-1-value['unpublished']
                p.require(finished>=value['acknowledgedThrough'],'batch_reserved_census')
                expected_count=min(p.BATCH_RECORDS,finished-value['acknowledgedThrough'])
                p.require(len(rows)==expected_count,'batch_prefix_count')
                p.require(type(terminal_bytes) is list and len(terminal_bytes)<=p.BATCH_RECORDS,'terminal_count')
                staged={};last=0;next_seq=self._ack+1;ticks=self._ticks;tracked=self._tracked
                for position,row in enumerate(rows):
                    raw=p.validate_record(row,config);seq=row['sequence']
                    p.require(seq==value['acknowledgedThrough']+position+1,'batch_prefix_sequence')
                    p.require(last<seq<value['nextReservedSequence'],'record_order');last=seq
                    if seq in self._records:
                        p.require(raw==self._records[seq]['raw'],'conflicting_duplicate');continue
                    p.require(seq==next_seq,'missing_sequence');next_seq+=1
                    request=row['binding']['requestId'];proposal=self._proposals.get(request)
                    p.require(proposal is not None and proposal['phase']=='admitted' and proposal['sequence'] is None,'no_current_admission')
                    p.require(p.canonical(row['binding'])==proposal['binding'],'proposal_binding')
                    p.require(not any(r['binding']['requestId']==request for r in staged.values()),'duplicate_step')
                    p.require(row['dispatchStartedTicks']>=ticks,'record_clock_regressed');ticks=row['publicationTicks']
                    p.require(p.canonical(row['trackedBefore'])==tracked,'client_tracked_chain')
                    tracked=p.canonical(row['trackedAfter'])
                    staged[seq]=row
                terminals={}
                for raw in terminal_bytes:
                    term=p.decode(raw,4096);raw=p.validate_terminal(term,config);request=term['binding']['requestId']
                    proposal=self._proposals.get(request)
                    p.require(proposal is not None and proposal['phase'] not in ('proposed','not_submitted'),'terminal_without_admission')
                    p.require(p.canonical(term['binding'])==proposal['binding'],'terminal_binding')
                    if request in self._terminals:
                        p.require(raw==self._terminals[request]['raw'],'terminal_conflict');continue
                    p.require(request not in terminals,'terminal_repeated_in_batch')
                    candidates=[seq for seq,row in staged.items() if row['binding']['requestId']==request]
                    seq=candidates[0] if candidates else proposal['sequence']
                    p.require(term['applicationSequences']==([] if seq is None else [seq]),'terminal_link')
                    if seq is not None:
                        application=staged.get(seq) or p.decode(self._records[seq]['raw'])
                        p.require(term['publicationTicks']>=application['publicationTicks'],'terminal_publication_clock')
                    terminals[request]=(term,raw)
                # Validation is atomic. A valid partial record is retained/ACKable but never publishable.
                for seq,row in staged.items():
                    request=row['binding']['requestId'];proposal=self._proposals[request]
                    disposition='validated_waiting_publication' if row['outcome']=='complete_returned' else 'quarantined_input_uncertainty'
                    self._records[seq]=dict(raw=p.canonical(row),observedClientNs=observed_client_ns,disposition=disposition)
                    proposal['sequence']=seq;proposal['phase']='application_reported'
                    if row['outcome']!='complete_returned':self._poison('partial_or_unknown_application')
                    self._ack=seq
                for request,(term,raw) in terminals.items():
                    self._terminals[request]=dict(raw=raw,observedClientNs=observed_client_ns)
                    proposal=self._proposals[request];proposal['terminal']=term['status']
                    if (term['status']!='completed' or term['reason']!='horizon_complete' or proposal['sequence'] is None
                            or term['releaseOutcome']!='returned_unverified'):
                        self._poison('terminal_requires_quarantine')
                if value['authorityLost']:self._poison('producer_authority_lost')
                self._tracked=tracked;self._ticks=ticks;self._server_ack=value['acknowledgedThrough'];self._observed=observed_client_ns
                self._next_reserved=value['nextReservedSequence']
                return self._ack
            except BaseException as error:
                self._poison(type(error).__name__,batch_bytes if type(batch_bytes) is bytes else b'')
                raise

    def publish(self,sequence,token,commit):
        """Consume one retained record once; callback is an unqualified external integration seam.

        A real callback must retain the original prepared frame/raw IDs/predecessor,
        exclusive RNG lease and all native guards. These are NOT implemented here.
        Callback failure is publication-unknown; there is no retry or rollback API.
        """
        with self._lock:
            self._ready();entry=self._records[sequence];record=p.decode(entry['raw'])
            proposal=self._proposals[record['binding']['requestId']]
            p.require(token is proposal['token'] and not proposal['attempted'],'publication_token_once')
            p.require(record['outcome']=='complete_returned','publication_uncertain')
            for other in self._proposals.values():
                if other['publishedGeneration'] is not None and other['terminal'] is None:
                    raise p.ProtocolError('earlier_terminal_unresolved')
            proposal['attempted']=True;self._publishing=True
        try:
            # No bridge/model callback runs under the ledger lock.
            result=commit(token,entry['raw'])
            p.require(type(result) is bytes and len(result)==32,'publication_state_digest')
        except BaseException as error:
            with self._lock:
                self._publishing=False;entry['disposition']='publication_unknown';self._poison(type(error).__name__)
            raise
        with self._lock:
            self._publishing=False
            if self._quarantine is not None:
                entry['disposition']='publication_unknown';raise p.ProtocolError('publication_concurrent_uncertainty')
            self._generation+=1;proposal['publishedGeneration']=self._generation;proposal['phase']='published'
            entry['disposition']='published';entry['stateDigest']=result.hex();entry['publishedGeneration']=self._generation
            return self._generation

    def snapshot(self,*,cutoff_client_ns):
        """Take a current atomic snapshot, not a historical query; caller supplies fresh knowledge time."""
        with self._lock:
            p.integer(cutoff_client_ns,max(self._observed,self._snapshot_cutoff))
            self._snapshot_cutoff=cutoff_client_ns
            rows=[dict(sequence=n,record=p.decode(v['raw']),observedClientNs=v['observedClientNs'],disposition=v['disposition'],
                publishedGeneration=v.get('publishedGeneration'),stateDigest=v.get('stateDigest'))
                for n,v in self._records.items() if v['observedClientNs']<=cutoff_client_ns]
            terminals=[dict(record=p.decode(v['raw']),observedClientNs=v['observedClientNs'])
                for v in self._terminals.values() if v['observedClientNs']<=cutoff_client_ns]
            return p.canonical(dict(version=p.VERSION,cutoffClientNs=cutoff_client_ns,records=rows,
                terminals=terminals,acknowledgedThrough=self._ack,quarantine=self._quarantine,
                publicationCount=self._generation),512*1024)

    @property
    def quarantined(self):
        """Public status is conservative and independent of physical held/release state."""
        with self._lock:return self._quarantine is not None
