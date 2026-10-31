"""Inert codec, teacher-forcing and transactional feedback regressions."""
import ast
from copy import deepcopy
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import NamedTuple
import unittest

import torch
from torch.utils import _pytree

from model_adapters import OpenP2PAdapter
from p2p_executed_history import (MODE, KEYBOARD, ExecutedHistoryCadence, encode_controller_step, executed_history_policy,
                                  source_after_terminal, teacher_forced_step,
                                  validate_action_mapping, verify_completed_receipt)
import test_p2p_action_codec as official


def step(keys=None, dx=0, dy=0, hold=50):
    """Make a single controller step without any hidden repair or scroll fields."""
    return dict(durationMs=hold, keys=[] if keys is None else keys, mouseDx=dx, mouseDy=dy)


def receipt_fixture(selected=None):
    """Describe one completed software interval, without asserting physical delivery."""
    selected = step(['W']) if selected is None else selected
    request = dict(requestId='request-1', frameId=1, modelId='hybrid-native', steps=[selected],
                   observedAtMs=80., startBeforeMs=220., expiresAtMs=780.)
    accepted = dict(type='accepted', requestId='request-1', acceptedAtMs=100.)
    receipt = dict(requestId='request-1', frameId=1, modelId='hybrid-native',
                   acceptedAtMs=100., endedAtMs=100.+selected['durationMs'],
                   status='completed', reason='horizon_complete', appliedSteps=[dict(
                       index=0, startedAtMs=100.1, keys=selected['keys'][:],
                       mouseDx=selected['mouseDx'], mouseDy=selected['mouseDy'])])
    return request, accepted, receipt


class ExecutedCadenceTests(unittest.TestCase):
    """Sampling waits retain a prediction permit instead of spending another decision period."""
    def test_startup_sampling_does_not_invent_prediction_slots(self):
        cadence = ExecutedHistoryCadence(10, 1.)
        for now in (1., 1.005, 1.04, 1.12):
            cadence.advance(now)
            self.assertAlmostEqual(cadence.next_at, now+.005)
            self.assertAlmostEqual(cadence.remaining(now), .005)
        cadence.prediction_started(1.125)
        cadence.advance(1.15)
        self.assertAlmostEqual(cadence.next_at, 1.225)

    def test_repeated_source_waits_preserve_the_same_minimum_start_time(self):
        cadence = ExecutedHistoryCadence(10, 0.)
        cadence.prediction_started(0.)
        for now in (.025, .060, .080):
            cadence.advance(now)
            self.assertAlmostEqual(cadence.next_at, .100)
        for now in (.100, .105, .120):
            cadence.advance(now)
            self.assertAlmostEqual(cadence.next_at, now+.005)
        cadence.prediction_started(.125)
        cadence.advance(.150)
        self.assertAlmostEqual(cadence.next_at, .225)

    def test_slow_receipt_rebases_without_catchup_or_an_extra_full_period(self):
        cadence = ExecutedHistoryCadence(10, 0.)
        cadence.prediction_started(0.)
        cadence.advance(.340)
        self.assertAlmostEqual(cadence.next_at, .345)
        cadence.prediction_started(.345)
        cadence.advance(.350)
        self.assertAlmostEqual(cadence.next_at, .445)
        with self.assertRaisesRegex(RuntimeError, 'before its cadence'):
            cadence.prediction_started(.400)
        cadence.prediction_started(.445)
        cadence.advance(.470)
        self.assertAlmostEqual(cadence.next_at, .545)

    def test_both_hold_lengths_share_the_prediction_rate_limit(self):
        for hold in (50, 60):
            with self.subTest(hold=hold):
                cadence = ExecutedHistoryCadence(10, 0.)
                cadence.prediction_started(0.)
                # Receipt arrival includes inference and the commanded horizon;
                # neither the terminal poll nor a source retry consumes a new slot.
                cadence.advance(.025+hold/1000)
                self.assertAlmostEqual(cadence.next_at, .100)
                cadence.advance(.105)
                self.assertAlmostEqual(cadence.next_at, .110)
                cadence.prediction_started(.110)
                cadence.advance(.120)
                self.assertAlmostEqual(cadence.next_at, .210)

    def test_invalid_frequencies_and_early_predictions_are_rejected(self):
        for hz in (0, -1, True, float('nan'), float('inf'), '10'):
            with self.subTest(hz=hz), self.assertRaises(ValueError):
                ExecutedHistoryCadence(hz, 0.)
        cadence = ExecutedHistoryCadence(10, 1.)
        with self.assertRaisesRegex(RuntimeError, 'before its cadence'):
            cadence.prediction_started(.99)


class ExecutedCodecTests(unittest.TestCase):
    """The independently frozen JSON codec agrees with upstream for actual integer inputs."""
    @classmethod
    def setUpClass(cls):
        """Load only upstream action definitions, never a checkpoint or a CUDA device."""
        official.OfficialMouseDecoderTests.setUpClass()
        cls.mapping = official.OfficialMouseDecoderTests.mapping

    def test_descriptor_is_explicit_and_rejects_other_holds(self):
        for hold in (50, 60):
            self.assertEqual(executed_history_policy(hold)['historyCommitMode'], MODE)
            self.assertEqual(executed_history_policy(hold)['maxPendingActions'], 1)
        for hold in (True, 50., 33, 100, None):
            with self.subTest(hold=hold), self.assertRaises(ValueError):
                executed_history_policy(hold)

    def test_every_supported_key_and_zero_mouse_match_upstream(self):
        validate_action_mapping(self.mapping)
        for key, (original, _) in KEYBOARD.items():
            actual = encode_controller_step(step([key]))
            reference = self.mapping.action_to_tensor([original], [], SimpleNamespace(x=torch.tensor(0), y=torch.tensor(0)))
            self.assertEqual(actual['keys'], reference.keys[0].tolist())
            self.assertEqual(actual['mouseDxBin'], reference.mouse_delta_x.item())
            self.assertEqual(actual['mouseDyBin'], reference.mouse_delta_y.item())
        actual = encode_controller_step(step(['W', 'LBUTTON', 'RBUTTON']))
        self.assertEqual(actual['mouseButtons'], [1, 2])
        self.assertNotEqual((actual['mouseDxBin'], actual['mouseDyBin']), (0, 0))

    def test_integer_mouse_edges_match_without_duration_rescaling(self):
        for axis, values in (('x', range(-600, 601)), ('y', range(-200, 201))):
            for value in values:
                dx, dy = (value, 0) if axis == 'x' else (0, value)
                actual = encode_controller_step(step(dx=dx, dy=dy))
                reference = self.mapping.action_to_tensor([], [], SimpleNamespace(x=torch.tensor(dx), y=torch.tensor(dy)))
                self.assertEqual(actual['mouseDxBin'], reference.mouse_delta_x.item())
                self.assertEqual(actual['mouseDyBin'], reference.mouse_delta_y.item())
        self.assertEqual(encode_controller_step(step(['W'], 34, hold=50)),
                         encode_controller_step(step(['W'], 34, hold=100)))

    def test_unsupported_or_lossy_steps_are_refused(self):
        cases = [step([key]) for key in ('X', 'LCONTROL', 'ESCAPE', 'F1', 'w', '5', 'SHIFT')]
        cases += [step(['W', 'W']), step(['A', 'D', 'E', 'F', 'Q']),
                  step(['LBUTTON', 'RBUTTON', 'MBUTTON']), step(dx=1.5), step(dx=True),
                  step(dx=2**31), step(hold=101), step(hold=True), dict(step(), scroll=0)]
        for selected in cases:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                encode_controller_step(selected)

    def test_changed_installed_mapping_is_not_silently_supported(self):
        changed = deepcopy(self.mapping)
        changed.keyboard_reverse_map[11] = 'x'
        with self.assertRaises(ValueError):
            validate_action_mapping(changed)
        changed = deepcopy(self.mapping)
        changed._mouse_delta_x_edges[12] = 2
        with self.assertRaises(ValueError):
            validate_action_mapping(changed)


class NativeReceiptTests(unittest.TestCase):
    """A declared accepted request is insufficient to label action history."""
    def test_only_completed_single_step_is_positive(self):
        request, accepted, receipt = receipt_fixture()
        self.assertEqual(verify_completed_receipt(receipt, request, accepted), receipt)
        # The native horizon is based on admission. Actual start was later, so
        # completion does not assert a full fifty milliseconds of keyboard hold.
        self.assertLess(receipt['endedAtMs']-receipt['appliedSteps'][0]['startedAtMs'], 50)
        cases = [dict(receipt, status='replaced', reason='newer_proposal'),
                 dict(receipt, status='cancelled', reason='client_release'),
                 dict(receipt, requestId='other'), dict(receipt, frameId=True),
                 dict(receipt, modelId='open-p2p'), dict(receipt, acceptedAtMs=float('nan')),
                 dict(receipt, endedAtMs=149), dict(receipt, endedAtMs=780),
                 dict(receipt, appliedSteps=[]), dict(receipt, appliedSteps=receipt['appliedSteps']*2)]
        for item in cases:
            with self.subTest(receipt=item), self.assertRaises(ValueError):
                verify_completed_receipt(item, request, accepted)

    def test_partial_wrong_and_late_native_steps_are_refused(self):
        request, accepted, receipt = receipt_fixture()
        for change in (dict(keys=['A']), dict(mouseDx=1), dict(mouseDy=True), dict(index=True),
                       dict(startedAtMs=99), dict(startedAtMs=221), dict(startedAtMs=float('inf'))):
            candidate = dict(receipt, appliedSteps=[dict(receipt['appliedSteps'][0], **change)])
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_completed_receipt(candidate, request, accepted)
        with self.assertRaises(ValueError):
            verify_completed_receipt(receipt, dict(request, observedAtMs=101), accepted)
        with self.assertRaises(ValueError):
            verify_completed_receipt(receipt, {key:value for key,value in request.items() if key != 'observedAtMs'}, accepted)

    def test_post_terminal_source_requires_all_three_freshness_witnesses(self):
        previous = dict(requestId='old', frameId=10, endedAtMs=150,
                        sourceFrame=dict(captureEpoch='same', timestamp100ns=1000))
        frame = dict(frameId=11, sourceFrame=dict(captureEpoch='same', timestamp100ns=2000))
        self.assertTrue(source_after_terminal(frame, 151, previous))
        self.assertFalse(source_after_terminal(frame, 150, previous))
        self.assertFalse(source_after_terminal(dict(frame, frameId=10), 151, previous))
        self.assertFalse(source_after_terminal(dict(frame, sourceFrame=previous['sourceFrame']), 151, previous))
        with self.assertRaises(ValueError):
            source_after_terminal(dict(frame, sourceFrame=dict(captureEpoch='new', timestamp100ns=2000)), 151, previous)


class CacheState(NamedTuple):
    """Small CPU KV state with the same public fields as upstream."""
    k_cache: torch.Tensor
    v_cache: torch.Tensor


class ImageTokens:
    """One deterministic visual token, used by both actual upstream and local passes."""
    def get_n_img_tokens(self):
        """Expose the same one-token configuration as the installed checkpoint."""
        return 1

    def __call__(self, frame):
        """Retain image-dependent values without a vision model or GPU."""
        return frame.mean().expand(1, 1, 1, 4) + torch.arange(4).view(1, 1, 1, 4)


class TemporalCore:
    """Two coupled layers make an action-only KV tail patch observably incorrect."""
    def forward(self, tokens, *, input_pos, kv_cache_state, should_grow_cache, use_decode_mask):
        """Roll exactly one full timestep and retain complete per-layer state."""
        assert not should_grow_cache and use_decode_mask
        output, states = tokens, []
        for state in kv_cache_state:
            output = torch.cumsum(output*.125 + state.v_cache.mean(dim=(1, 2)).unsqueeze(1), dim=1)
            keys = output.unsqueeze(1) + input_pos.view(1, 1, -1, 1)*.001
            values = output.unsqueeze(1)*.5
            states.append(CacheState(torch.cat((state.k_cache[:, :, 12:], keys), dim=2),
                                     torch.cat((state.v_cache[:, :, 12:], values), dim=2)))
        return output, states


def toy_model(history=3):
    """Exercise the installed full online_forward with tiny deterministic CPU components."""
    source = Path(__file__).resolve().parents[2] / 'artifacts/agent/sources/open-p2p/elefant/policy_model/policy_transformer.py'
    if not source.is_file():
        raise unittest.SkipTest('Official Open P2P source checkout is required')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(node for parent in tree.body if isinstance(parent, ast.ClassDef)
                  for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == 'online_forward')
    def assert_shape(actual, expected):
        """Check upstream shape assertions even though no model weights are loaded."""
        assert actual == expected, (actual, expected)
    namespace = dict(torch=torch, pytree=_pytree, eager_assert=assert_shape)
    exec(compile(ast.Module(body=ast.parse('from __future__ import annotations').body+[method], type_ignores=[]), str(source), 'exec'), namespace)
    official.OfficialMouseDecoderTests.setUpClass()
    mapping = official.OfficialMouseDecoderTests.mapping
    transformer = SimpleNamespace(config=SimpleNamespace(embed_dim=4, n_thinking_tokens=1, n_action_tokens=8),
        image_tokenizer=ImageTokens(), img_pos_tokens=torch.ones(1, 1, 4)*.1,
        text_token_size=1, text_tokenizer_embed_dim=4, device=torch.device('cpu'),
        text_embed_mlp=lambda value: value*.3, _impute_no_text_embedding=lambda value: value,
        text_pos_tokens=torch.ones(1, 1, 4)*.2, thinking_pos_tokens=torch.ones(1, 1, 4)*.3,
        action_out_token=torch.ones(1, 1, 4)*.4, action_pos_tokens=torch.ones(1, 8, 4)*.5,
        kv_cache=SimpleNamespace(max_seq_len=history*12, step_size=12), _transformer=TemporalCore())
    transformer.online_forward = MethodType(namespace['online_forward'], transformer)
    model = SimpleNamespace(bc_transformer=transformer, action_mapping=mapping,
        _normalize_frames=lambda frame: frame.float()/255)
    model.action_in_to_tokens = lambda action: torch.cat(tuple(action), dim=2).float().unsqueeze(-1)*torch.arange(1, 5)
    states = [CacheState(torch.zeros(1, 1, history*12, 4), torch.zeros(1, 1, history*12, 4)) for _ in range(2)]
    return model, states


def reference_step(model, frame, idx, state, text, selected):
    """Run the unmodified upstream two-pass path with a deterministic selected action."""
    action = model.action_mapping.action_to_tensor(
        [KEYBOARD[key][0] for key in selected['keys'] if key in KEYBOARD],
        [str({'LBUTTON': 0, 'RBUTTON': 1, 'MBUTTON': 2}[key]) for key in selected['keys'] if key not in KEYBOARD],
        SimpleNamespace(x=torch.tensor(selected['mouseDx']), y=torch.tensor(selected['mouseDy'])))
    # Upstream decoder deltas have B,C shape, while its training encoder emits C.
    action = type(action)(action.keys, action.mouse_buttons, action.mouse_delta_x.reshape(1, 1), action.mouse_delta_y.reshape(1, 1))
    model.bc_transformer.action_decoder = SimpleNamespace(autogressive_sample=lambda *args, **kwargs: action)
    _, next_idx, next_state = model.bc_transformer.online_forward(
        model._normalize_frames(frame).unsqueeze(0).unsqueeze(0), text, idx, state,
        should_grow_cache=False, action_sampler=None, empty_sampled_action_fn=model.action_mapping.make_empty_action,
        action_in_to_tokens_fn=model.action_in_to_tokens)
    return next_idx, next_state


class TeacherForcedHistoryTests(unittest.TestCase):
    """The replacement preserves complete visual context without keeping a counterfactual sample."""
    def test_rebuild_matches_upstream_empty_partial_full_and_rolling_histories(self):
        for history in (1, 3, 41):
            model, state = toy_model(history)
            idx, text = torch.tensor(0), torch.ones(1, 4)
            for index in range(history+2):
                frame = torch.full((3, 2, 2), index % 255, dtype=torch.uint8)
                selected = step(['W'] if index % 2 else [], dx=34 if index % 2 == 0 else 0)
                expected_idx, expected = reference_step(model, frame, idx, state, text, selected)
                actual_idx, actual = teacher_forced_step(model, frame, idx, state, text, encode_controller_step(selected))
                self.assertEqual(actual_idx.item(), (index+1)*12)
                for got, want in zip(actual, expected):
                    torch.testing.assert_close(got.k_cache, want.k_cache, rtol=0, atol=0)
                    torch.testing.assert_close(got.v_cache, want.v_cache, rtol=0, atol=0)
                idx, state = actual_idx, actual

    def make_policy(self):
        """Construct an adapter transaction on CPU, without running its model constructor."""
        model, state = toy_model()
        policy = object.__new__(OpenP2PAdapter)
        policy.model, policy.state, policy.idx = model, state, torch.tensor(0)
        policy.static_state, policy.static_idx, policy.graph = state, policy.idx, object()
        policy.text = torch.ones(1, 4)
        policy._goal_tensor = policy.text.clone()
        policy.temporal_cache = SimpleNamespace(valid_tokens=torch.tensor(0))
        policy.temporal_cache.reset = lambda: policy.temporal_cache.valid_tokens.zero_()
        policy.config = SimpleNamespace(shared=SimpleNamespace(n_seq_timesteps=3))
        policy.execution_feedback = policy.executed_history = True
        policy._pending_feedback, policy._history_backup, policy._executed_candidate = False, None, None
        policy.steps_seen = 0
        policy._executed_forward = MethodType(lambda self, encoded: teacher_forced_step(
            self.model, self.static_frame, self._backup_idx, self._history_backup, self.text, encoded), policy)
        return policy

    def predict_sample(self, policy):
        """Create a deliberately counterfactual sample using the full upstream path."""
        policy._begin_history_transaction()
        policy.temporal_cache.valid_tokens.add_(12).clamp_(max=36)
        policy.static_frame = torch.full((3, 2, 2), 80+policy.steps_seen, dtype=torch.uint8)
        idx, states = reference_step(policy.model, policy.static_frame, policy.idx, policy.state,
                                    policy.text, step(['SPACE', 'RBUTTON']))
        policy.idx.copy_(idx)
        for current, new in zip(policy.state, states):
            current.k_cache.copy_(new.k_cache)
            current.v_cache.copy_(new.v_cache)
        policy.steps_seen += 1

    def test_native_override_commits_actual_action_and_preserves_graph_storage(self):
        policy = self.make_policy()
        pointers = [policy.idx.data_ptr(), policy.text.data_ptr(), policy.temporal_cache.valid_tokens.data_ptr()]
        pointers += [part.k_cache.data_ptr() for part in policy.state]
        for index in range(5):
            self.predict_sample(policy)
            sampled = policy.state[1].k_cache.clone()
            request, accepted, receipt = receipt_fixture(step(['W']))
            encoded = policy.prepare_executed_action(request['steps'][0])
            self.assertNotEqual(sampled.tolist(), policy.state[1].k_cache.tolist())
            encoded['keys'][0] = 999  # Returned evidence cannot mutate the private staged label.
            with self.assertRaises(RuntimeError):
                policy._begin_history_transaction()
            with self.assertRaises(RuntimeError):
                policy.finish_action(True)
            policy.finish_executed_action(receipt, request, accepted)
            counters = policy.executed_history_counters()
            self.assertEqual(counters['afterFrames'], index+1)
            self.assertEqual(counters['validFrames'], min(index+1, 3))
            self.assertEqual(counters['afterIndex'], (index+1)*12)
        self.assertEqual(pointers, [policy.idx.data_ptr(), policy.text.data_ptr(), policy.temporal_cache.valid_tokens.data_ptr()]
                         + [part.k_cache.data_ptr() for part in policy.state])

    def test_rejection_restores_prior_cache_and_invalid_receipt_cannot_commit(self):
        policy = self.make_policy()
        self.predict_sample(policy)
        request, accepted, receipt = receipt_fixture()
        policy.prepare_executed_action(request['steps'][0])
        with self.assertRaises(ValueError):
            policy.finish_executed_action(dict(receipt, status='replaced'), request, accepted)
        self.assertTrue(policy._pending_feedback)
        policy.finish_action(False)
        self.assertEqual(policy.executed_history_counters()['afterFrames'], 0)
        self.assertEqual(policy.idx.item(), 0)
        self.assertEqual(policy.temporal_cache.valid_tokens.item(), 0)
        self.assertTrue(all(torch.count_nonzero(part.k_cache).item() == 0 for part in policy.state))
        self.predict_sample(policy)
        policy.prepare_executed_action(request['steps'][0])
        policy.reset()
        self.assertFalse(policy._pending_feedback)
        self.assertIsNone(policy._executed_candidate)


if __name__ == '__main__':
    unittest.main()
