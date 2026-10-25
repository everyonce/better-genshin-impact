"""INERT_ONLY post-enable connection ownership cases; prepared, never live evidence."""
import copy
import types
import unittest

import test_step_application_handshake as h


class ConnectionCorrectionTests(unittest.TestCase):
    """Use the actual Bridge AST, unchanged intake and deterministic fake I/O callbacks."""
    def ready(self):
        """Negotiate a synthetic channel and leave one complete synthetic status packet."""
        status=dict(type='status',stepApplications=h.enabled()['stepApplications'],stepApplicationTerminals=[])
        value,owned,gate,namespace=h.bridge(extra=h.packet(status))
        intake=value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        return value,owned,gate,namespace,intake,status

    def reject(self,value,owned,intake,foreign=None):
        """Identity loss must be sticky uncertainty, with no replacement-handle cleanup."""
        with self.assertRaises(ValueError) as caught:value.request('status')
        self.assertEqual(str(caught.exception),'experimental_original_connection')
        self.assertIs(value._experimental_enable_error,caught.exception)
        self.assertTrue(value._experimental_enable_failed)
        self.assertTrue(intake.ledger.quarantined)
        self.assertEqual(owned.close_calls,1)
        self.assertEqual(intake._ack,0);self.assertEqual(intake._terminal_ack,[])
        if foreign is not None:
            self.assertEqual(foreign.sent,b'');self.assertEqual(foreign.close_calls,0)
        return caught.exception

    def test_intact_connection_accepts_complete_status(self):
        value,owned,gate,_,intake,status=self.ready();raw=value._hello_raw
        response,pixels=value.request('status')
        self.assertEqual((response,pixels),(status,b''));self.assertFalse(intake.ledger.quarantined)
        self.assertEqual(owned.close_calls,0);self.assertIs(value._hello_raw,raw)
        self.assertEqual([row['command'] for row in owned.requests()],['enableStepApplications','status'])
        self.assertEqual(owned.requests()[1]['stepApplicationsAck']['through'],0)
        self.assertFalse(gate.held)

    def test_enable_reply_reads_only_captured_handle_after_callback_swap(self):
        value,owned,_,_=h.bridge();foreign=h.MemoryPipe(b'');reads=[]
        def foreign_read(size):raise AssertionError('foreign enable read')
        foreign.read=foreign_read
        def changed():reads.append(True);value.handle=foreign
        owned.on_read=changed
        with self.assertRaises(ValueError) as caught:
            value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        self.assertEqual(str(caught.exception),'experimental_enable_original_connection')
        self.assertEqual(len(reads),2)
        self.assertIsNone(getattr(value,'_step_application_intake',None))
        self.assertEqual(owned.close_calls,1)
        self.assertEqual(foreign.close_calls,0);self.assertEqual(foreign.sent,b'')

    def test_handle_replacement_prevents_preparation_and_keeps_pending_uncertain(self):
        value,owned,_,_,intake,_=self.ready();sent=bytes(owned.sent)
        foreign=h.MemoryPipe(b'');value.handle=foreign
        pending=('pending',object(),b'synthetic-unwritten-label');intake._action=pending
        def forbidden(*args,**kwargs):raise AssertionError('preparation/classification reached')
        intake.prepare=forbidden;intake.failed=forbidden
        self.reject(value,owned,intake,foreign)
        self.assertEqual(owned.sent,sent);self.assertIs(intake._action,pending)

    def test_equal_hello_replacement_or_content_mutation_prevents_write(self):
        for replace in (False,True):
            with self.subTest(replace=replace):
                value,owned,_,_,intake,_=self.ready();sent=bytes(owned.sent)
                if replace:value.hello=copy.deepcopy(value.hello)
                else:value.hello['ownerEpoch']='foreign'
                self.reject(value,owned,intake);self.assertEqual(owned.sent,sent)

    def test_waiting_request_rechecks_identity_after_lock_acquisition(self):
        value,owned,gate,_,intake,_=self.ready();foreign=h.MemoryPipe(b'');sent=bytes(owned.sent)
        gate.before_enter=lambda:setattr(value,'handle',foreign)
        self.reject(value,owned,intake,foreign);self.assertEqual(owned.sent,sent)
        self.assertFalse(gate.held)

    def test_prepare_callback_cannot_redirect_the_write(self):
        value,owned,_,_,intake,_=self.ready();foreign=h.MemoryPipe(b'');sent=bytes(owned.sent)
        prepare=intake.prepare
        def changed(request):
            result=prepare(request);value.handle=foreign;return result
        intake.prepare=changed
        self.reject(value,owned,intake,foreign);self.assertEqual(owned.sent,sent)

    def test_partial_write_identity_change_stops_on_original_handle(self):
        value,owned,_,_,intake,_=self.ready();foreign=h.MemoryPipe(b'');length=len(owned.sent)
        owned.chunk=3;owned.on_write=lambda:setattr(value,'handle',foreign)
        self.reject(value,owned,intake,foreign)
        self.assertEqual(len(owned.sent),length+3)

    def test_read_handle_change_cannot_read_foreign_or_ingest(self):
        value,owned,_,_,intake,_=self.ready();foreign=h.MemoryPipe(b'');received=[]
        def foreign_read(size):raise AssertionError('foreign read')
        foreign.read=foreign_read
        intake.receive=lambda *a,**k:received.append((a,k))
        owned.on_read=lambda:setattr(value,'handle',foreign)
        self.reject(value,owned,intake,foreign);self.assertEqual(received,[])

    def test_hello_changes_after_body_read_cannot_ingest(self):
        for replace in (False,True):
            with self.subTest(replace=replace):
                value,owned,_,_,intake,_=self.ready();reads=[];received=[]
                intake.receive=lambda *a,**k:received.append((a,k))
                def changed():
                    reads.append(True)
                    if len(reads)==2:
                        if replace:value.hello=copy.deepcopy(value.hello)
                        else:value.hello['goalVersion']=2
                owned.on_read=changed
                self.reject(value,owned,intake)
                self.assertEqual(len(reads),2);self.assertEqual(received,[])

    def test_final_clock_callback_identity_change_is_rejected_before_intake(self):
        value,owned,_,namespace,intake,_=self.ready();foreign=h.MemoryPipe(b'');received=[]
        intake.receive=lambda *a,**k:received.append((a,k))
        def clock():value.handle=foreign;return 3000
        namespace['time']=types.SimpleNamespace(perf_counter_ns=clock)
        self.reject(value,owned,intake,foreign);self.assertEqual(received,[])

    def test_primary_identity_error_survives_both_cleanup_errors_once(self):
        value,owned,_,_,intake,_=self.ready();foreign=h.MemoryPipe(b'');value.handle=foreign
        quarantine=RuntimeError('fake quarantine');close=OSError('fake close')
        def uncertain(reason):raise quarantine
        intake.ledger.uncertain=uncertain;owned.close_error=close
        with self.assertRaises(ValueError) as caught:value.request('status')
        self.assertEqual(str(caught.exception),'experimental_original_connection')
        self.assertIs(value._experimental_enable_error,caught.exception)

        self.assertIs(value._experimental_enable_intake_error,quarantine)
        self.assertIs(value._experimental_enable_close_error,close)
        self.assertEqual(len(caught.exception.__notes__),2)
        with self.assertRaises(RuntimeError):value.request('status')
        self.assertEqual(owned.close_calls,1);self.assertEqual(foreign.close_calls,0)
        self.assertIs(value._experimental_enable_error,caught.exception)

    def test_io_failure_plus_identity_loss_retains_io_primary_and_cleanup(self):
        for stage in ('write','read'):
            with self.subTest(stage=stage):
                value,owned,_,_,intake,_=self.ready();foreign=h.MemoryPipe(b'')
                original=OSError('original '+stage);cleanup=OSError('fake close');owned.close_error=cleanup
                def changed():value.handle=foreign;raise original
                if stage=='write':owned.on_write=changed
                else:owned.on_read=changed
                with self.assertRaises(OSError) as caught:value.request('status')
                self.assertIs(caught.exception,original)
                self.assertIs(value._experimental_enable_error,original)
                self.assertIs(value._experimental_enable_close_error,cleanup)
                self.assertEqual(str(value._experimental_connection_error),'experimental_original_connection')
                self.assertTrue(intake.ledger.quarantined)
                self.assertEqual((owned.close_calls,foreign.close_calls),(1,0))
                self.assertEqual(foreign.sent,b'');self.assertEqual(intake._ack,0)

    def test_replaced_intake_does_not_replace_negotiated_ownership(self):
        value,owned,_,_,intake,_=self.ready();foreign=object();sent=bytes(owned.sent)
        value._step_application_intake=foreign
        self.reject(value,owned,intake);self.assertEqual(owned.sent,sent)
        self.assertIs(value._experimental_connection_identity[3],intake)

    def test_exact_h01_body_demonstrates_foreign_handle_request(self):
        saved=h.SOURCE
        try:
            h.SOURCE=h.HERE/'preimages/stream_client.py'
            value,owned,_,_,intake,status=self.ready()
        finally:h.SOURCE=saved
        foreign=h.MemoryPipe(h.packet(status));value.handle=foreign;sent=bytes(owned.sent)
        self.assertEqual(value.request('status'),(status,b''))
        self.assertEqual(len(foreign.requests()),1)
        self.assertIn('stepApplicationsAck',foreign.requests()[0])
        self.assertEqual(owned.sent,sent);self.assertFalse(intake.ledger.quarantined)
        self.assertEqual((owned.close_calls,foreign.close_calls),(0,0))

    def test_reenable_preserves_first_failure_and_cleanup_evidence(self):
        """Neither an initial failed enable nor later identity loss permits a second cleanup."""
        for stage in ('initial','post_enable'):
            with self.subTest(stage=stage):
                cleanup=OSError('original fake close');quarantine=RuntimeError('original fake quarantine')
                if stage=='initial':
                    value,owned,_,_=h.bridge();owned.fail_write=True;owned.close_error=cleanup
                    with self.assertRaises(OSError) as caught:
                        value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
                else:
                    value,owned,_,_,intake,_=self.ready();owned.close_error=cleanup
                    def uncertain(reason):raise quarantine
                    intake.ledger.uncertain=uncertain;value.handle=h.MemoryPipe(b'')
                    with self.assertRaises(ValueError) as caught:value.request('status')
                    self.assertIs(value._experimental_enable_intake_error,quarantine)
                original=caught.exception;notes=list(original.__notes__);sent=bytes(owned.sent)
                saved={key:item for key,item in vars(value).items() if key.startswith('_experimental_')}
                for unused in range(2):
                    with self.assertRaisesRegex(RuntimeError,'experimental_enable_connection_retired'):
                        value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
                self.assertEqual(set(saved),{key for key in vars(value) if key.startswith('_experimental_')})
                for key,item in saved.items():self.assertIs(getattr(value,key),item)
                self.assertIs(value._experimental_enable_error,original)
                self.assertIs(value._experimental_enable_close_error,cleanup)
                self.assertEqual(original.__notes__,notes);self.assertEqual(owned.close_calls,1)
                self.assertEqual(owned.sent,sent)

    def test_successful_reenable_retires_original_intake_and_handle_only_once(self):
        """Public owner replacements cannot become repeat-enable cleanup targets."""
        value,owned,_,_,intake,_=self.ready();sent=bytes(owned.sent);foreign=h.MemoryPipe(b'')
        calls=[]
        replacement=types.SimpleNamespace(ledger=types.SimpleNamespace(uncertain=lambda reason:calls.append(reason)))
        value._step_application_intake=replacement;value.handle=foreign
        with self.assertRaisesRegex(RuntimeError,'experimental_enable_single_attempt') as caught:
            value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        self.assertIs(value._experimental_enable_error,caught.exception)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(calls,[])
        self.assertIs(value._step_application_intake,replacement)
        self.assertIs(value._experimental_connection_identity[3],intake)
        self.assertEqual((owned.close_calls,foreign.close_calls),(1,0))
        self.assertEqual(owned.sent,sent);self.assertEqual(foreign.sent,b'')
        with self.assertRaisesRegex(RuntimeError,'experimental_enable_connection_retired'):
            value.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        self.assertIs(value._experimental_enable_error,caught.exception)
        self.assertEqual((owned.close_calls,foreign.close_calls),(1,0));self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
