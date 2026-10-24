"""Capture-option admission and lifecycle checks with fake transport only; no desktop actions."""
import io
import itertools
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class CaptureOptionsTests(unittest.TestCase):
    def setUp(self):
        self.child = {'processId':123, 'windowsSessionId':3, 'instanceNonce':'child-epoch',
            'instanceType':'ChildSession', 'remoteDesktop':True, 'automationEnabled':True,
            'runtimeRunning':True, 'automationState':'game_ready', 'taskRunning':False,
            'agentStreamRunning':False, 'captureMode':'WindowsGraphicsCaptureV2',
            'readbackVersion':1, 'readbackModes':['blocking','poll_single_v1'],
            'configuredReadbackMode':'blocking', 'effectiveReadbackMode':'blocking',
            'captureOptionsVersion':1, 'sourceRetentions':['disabled','hold-until-readback-v1'],
            'conversionModes':['gpu','cpu'], 'configuredSourceRetention':'disabled',
            'effectiveSourceRetention':'disabled', 'configuredConversion':'gpu', 'effectiveConversion':'gpu'}

    def selected(self, retention='hold-until-readback-v1', conversion='cpu'):
        return {**self.child, 'configuredSourceRetention':retention, 'effectiveSourceRetention':retention,
                'configuredConversion':conversion, 'effectiveConversion':conversion}

    def assert_preflight_rejects(self, child=None, **options):
        with patch.object(control, 'mutate') as mutate, patch.object(control, 'refresh') as refresh:
            with self.assertRaises(control.ControlError):
                control.set_capture_mode(self.child if child is None else child, 'WindowsGraphicsCaptureV2', 1, **options)
            mutate.assert_not_called(); refresh.assert_not_called()

    def test_wire_all_explicit_combinations_are_exact_and_nonce_bound(self):
        for retention, conversion, readback in itertools.product(control.SOURCE_RETENTIONS,
                control.CONVERSION_MODES, control.READBACK_MODES):
            with self.subTest(retention=retention, conversion=conversion, readback=readback):
                api = FakePipe(self.child); api.session = 3
                control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', api=api,
                    fields={'captureMode':'WindowsGraphicsCaptureV2', 'sourceRetention':retention,
                            'conversion':conversion, 'readbackMode':readback})
                self.assertEqual(api.request['targetNonce'], 'child-epoch')
                self.assertEqual(api.request['sourceRetention'], retention)
                self.assertEqual(api.request['conversion'], conversion)

    def test_wire_null_types_aliases_unknown_fields_and_other_commands_never_connect(self):
        invalid = []
        for name in ('sourceRetention', 'conversion'):
            invalid += [('setCaptureMode', {'captureMode':'WindowsGraphicsCaptureV2', name:value})
                        for value in (None, True, 1, 1.0, [], {}, '', 'GPU', 'immediate-release-v1')]
            invalid += [('setCaptureMode', {'captureMode':'BitBlt', name:'gpu' if name=='conversion' else 'disabled'}),
                        ('status', {name:'gpu'}), ('setCaptureMode', {name:'gpu'})]
        invalid.append(('setCaptureMode', {'captureMode':'WindowsGraphicsCaptureV2', 'extra':True}))
        for command, fields in invalid:
            with self.subTest(command=command, fields=fields):
                api = FakePipe(self.child); api.session = 3
                with self.assertRaises(control.ControlError):
                    control.exchange(command,123,3,nonce='child-epoch',fields=fields,api=api)
                self.assertFalse(hasattr(api,'pipe_name'))

    def test_helper_explicit_null_and_other_invalid_values_reject(self):
        for name in ('source_retention','conversion'):
            for value in (None, True, 1, 1.0, [], {}, '', 'GPU', 'immediate-release-v1'):
                with self.subTest(name=name,value=value): self.assert_preflight_rejects(**{name:value})

    def test_explicit_option_requires_capability_before_mutation(self):
        legacy = {k:v for k,v in self.child.items() if k not in ('captureOptionsVersion','sourceRetentions',
            'conversionModes','configuredSourceRetention','effectiveSourceRetention','configuredConversion','effectiveConversion')}
        for options in ({'source_retention':'disabled'}, {'conversion':'gpu'}):
            self.assert_preflight_rejects(legacy, **options)
        with patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value=legacy):
            self.assertEqual(control.set_capture_mode(legacy,'WindowsGraphicsCaptureV2',1),legacy)
        mutate.assert_called_once_with('setCaptureMode',legacy,captureMode='WindowsGraphicsCaptureV2')

    def test_capability_version_is_exact_integer_one_even_when_options_omitted(self):
        for version in (None, True, False, 1.0, '1', 0, 2):
            with self.subTest(version=version):
                self.assert_preflight_rejects({**self.child,'captureOptionsVersion':version})

    def test_capability_lists_are_bounded_by_declared_choices_and_well_formed(self):
        for name in ('sourceRetentions','conversionModes'):
            for value in (None, [], '', [None], [1], ['gpu','gpu']):
                with self.subTest(name=name,value=value):
                    self.assert_preflight_rejects({**self.child,name:value})
        self.assert_preflight_rejects({**self.child,'sourceRetentions':['disabled']},source_retention='hold-until-readback-v1')
        self.assert_preflight_rejects({**self.child,'conversionModes':['gpu']},conversion='cpu')

    def test_saved_option_must_be_known_and_advertised_before_preserving_it(self):
        for name in ('configuredSourceRetention','configuredConversion'):
            for value in (None, True, 1, 'unknown'):
                with self.subTest(name=name,value=value): self.assert_preflight_rejects({**self.child,name:value})
        missing = dict(self.child); del missing['configuredConversion']
        self.assert_preflight_rejects(missing)

    def test_omitted_options_preserve_saved_values_but_readback_still_defaults_blocking(self):
        child = {**self.selected(),'configuredReadbackMode':'poll_single_v1','effectiveReadbackMode':'poll_single_v1'}
        ready = self.selected()
        with patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value=ready):
            self.assertEqual(control.set_capture_mode(child,'WindowsGraphicsCaptureV2',1),ready)
        mutate.assert_called_once_with('setCaptureMode',child,captureMode='WindowsGraphicsCaptureV2')

    def test_each_explicit_option_preserves_the_other_and_sends_only_supplied_fields(self):
        for options, ready, fields in (
                ({'source_retention':'hold-until-readback-v1'},self.selected(conversion='gpu'),{'sourceRetention':'hold-until-readback-v1'}),
                ({'conversion':'cpu'},self.selected(retention='disabled'),{'conversion':'cpu'})):
            with self.subTest(options=options), patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value=ready):
                self.assertEqual(control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1,**options),ready)
                mutate.assert_called_once_with('setCaptureMode',self.child,captureMode='WindowsGraphicsCaptureV2',**fields)

    def test_old_settings_during_lifecycle_wait_do_not_pretend_completed_attachment(self):
        changing = {**self.child,'automationState':'changing_capture','taskRunning':True,
                    'effectiveSourceRetention':None,'effectiveConversion':None}
        ready = self.selected()
        with patch.object(control,'mutate') as mutate, patch.object(control,'refresh',side_effect=[changing,ready]) as refresh, \
                patch.object(control.time,'sleep'):
            self.assertEqual(control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1,
                source_retention='hold-until-readback-v1',conversion='cpu'),ready)
        self.assertEqual(refresh.call_count,2); self.assertEqual(mutate.call_count,1)

    def test_capabilities_cannot_disappear_or_change_during_pending_lifecycle(self):
        changing = {**self.child,'automationState':'changing_capture','taskRunning':True}
        variants = [{**changing,'captureOptionsVersion':value} for value in (None,True,1.0,2)]
        variants += [{k:v for k,v in changing.items() if k!='captureOptionsVersion'},
                     {**changing,'sourceRetentions':['disabled']}, {**changing,'conversionModes':['cpu','gpu']}]
        for current in variants:
            with self.subTest(current=current), patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value=current):
                with self.assertRaises(control.ControlError): control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1)
                self.assertEqual(mutate.call_count,1)

    def test_completed_saved_and_effective_options_must_all_match(self):
        ready = self.selected()
        for name in ('configuredSourceRetention','effectiveSourceRetention','configuredConversion','effectiveConversion'):
            for value in (None,False,'unknown','disabled' if 'Retention' in name else 'gpu'):
                with self.subTest(name=name,value=value), patch.object(control,'mutate') as mutate, \
                        patch.object(control,'refresh',return_value={**ready,name:value}):
                    with self.assertRaises(control.ControlError):
                        control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1,
                            source_retention='hold-until-readback-v1',conversion='cpu')
                    self.assertEqual(mutate.call_count,1)

    def test_other_backend_preserves_saved_options_and_requires_no_effective_options(self):
        child = self.selected()
        for omit in (False,True):
            ready = {**child,'captureMode':'BitBlt','effectiveReadbackMode':None,
                     'effectiveSourceRetention':None,'effectiveConversion':None}
            if omit:
                del ready['effectiveSourceRetention']; del ready['effectiveConversion']
            with patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value=ready):
                self.assertEqual(control.set_capture_mode(child,'BitBlt',1),ready)
            mutate.assert_called_once_with('setCaptureMode',child,captureMode='BitBlt')
        for name in ('effectiveSourceRetention','effectiveConversion'):
            ready = {**child,'captureMode':'BitBlt','effectiveReadbackMode':None,'effectiveSourceRetention':None,'effectiveConversion':None,
                     name:'hold-until-readback-v1' if name.endswith('Retention') else 'cpu'}
            with patch.object(control,'mutate'), patch.object(control,'refresh',return_value=ready):
                with self.assertRaises(control.ControlError): control.set_capture_mode(child,'BitBlt',1)

    def test_explicit_options_never_apply_to_other_backends(self):
        for mode in control.CAPTURE_MODES:
            if mode=='WindowsGraphicsCaptureV2': continue
            for options in ({'source_retention':'disabled'},{'conversion':'gpu'}):
                with self.subTest(mode=mode,options=options), patch.object(control,'mutate') as mutate:
                    with self.assertRaises(control.ControlError): control.set_capture_mode(self.child,mode,1,**options)
                    mutate.assert_not_called()

    def test_role_idle_optin_and_task_guards_still_precede_mutation(self):
        for change in ({'taskRunning':True},{'taskRunning':None},{'agentStreamRunning':True},
                       {'instanceType':'Primary'},{'remoteDesktop':False},{'automationEnabled':False}):
            self.assert_preflight_rejects({**self.child,**change},source_retention='hold-until-readback-v1')

    def test_agent_start_or_failed_runtime_cannot_report_option_success(self):
        for change in ({'agentStreamRunning':True}, {'automationState':'failed','automationError':'fixture failure'}):
            with patch.object(control,'mutate') as mutate, patch.object(control,'refresh',return_value={**self.child,**change}):
                with self.assertRaises(control.ControlError): control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1)
                self.assertEqual(mutate.call_count,1)

    def test_uncertain_ack_never_replays_or_polls_for_success(self):
        with patch.object(control,'mutate',side_effect=control.ControlError('uncertain')) as mutate, patch.object(control,'refresh') as refresh:
            with self.assertRaises(control.ControlError):
                control.set_capture_mode(self.child,'WindowsGraphicsCaptureV2',1,conversion='cpu')
            self.assertEqual(mutate.call_count,1); refresh.assert_not_called()

    def test_cli_explicit_options_are_keyword_only_and_omission_keeps_old_call_shape(self):
        cases = [([],{}), (['--conversion','cpu'],{'conversion':'cpu'}),
                 (['--source-retention','disabled'],{'source_retention':'disabled'}),
                 (['--readback-mode','poll_single_v1','--source-retention','hold-until-readback-v1','--conversion','cpu'],
                  {'readback_mode':'poll_single_v1','source_retention':'hold-until-readback-v1','conversion':'cpu'})]
        for flags, options in cases:
            with self.subTest(flags=flags), patch.object(sys,'argv',['rdp_control.py','set-capture-mode','--mode','WindowsGraphicsCaptureV2']+flags), \
                    patch.object(sys,'stdout',io.StringIO()), patch.object(control,'discover',return_value={'instances':[self.child]}), \
                    patch.object(control,'set_capture_mode',return_value=self.child) as switch:
                self.assertEqual(control.main(),0)
            switch.assert_called_once_with(self.child,'WindowsGraphicsCaptureV2',120,**options)

    def test_cli_alias_is_rejected_before_discovery(self):
        for flags in (['--source-retention','immediate-release-v1'],['--conversion','GPU']):
            with patch.object(sys,'argv',['rdp_control.py','set-capture-mode','--mode','WindowsGraphicsCaptureV2']+flags), \
                    patch.object(sys,'stderr',io.StringIO()), patch.object(control,'discover') as discover:
                with self.assertRaises(SystemExit): control.main()
                discover.assert_not_called()


if __name__ == '__main__': unittest.main()
