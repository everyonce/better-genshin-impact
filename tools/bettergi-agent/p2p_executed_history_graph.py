"""Validated CUDA replay for a complete selected-action temporal timestep."""
import torch

from p2p_executed_history import encode_controller_step, teacher_forced_step


class ExecutedHistoryGraph:
    """Keep separate stable prior-state and action inputs for receipt-pending candidates."""

    def __init__(self, model, frame, index, state, text, dtype):
        """Prepare before any input lease, including startup without a history transaction."""
        self.model,self.frame,self.text,self.dtype=model,frame,text,dtype
        self.index=index.clone()
        self.state=[type(part)(part.k_cache.clone(),part.v_cache.clone()) for part in state]
        self.action_values=torch.zeros(8,dtype=torch.int64,device=frame.device)
        action_type=type(model.action_mapping.make_empty_action(1))
        self.action=action_type(self.action_values[:4].reshape(1,1,4),self.action_values[4:6].reshape(1,1,2),
                                self.action_values[6:7].reshape(1,1,1),self.action_values[7:8].reshape(1,1,1))
        initial=encode_controller_step(dict(durationMs=50,keys=[],mouseDx=0,mouseDy=0))
        self._copy_action(initial)
        stream=torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(2):expected=self._forward()
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        self.graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph,stream=stream):self.result=self._forward()
        self.graph.replay()
        torch.cuda.synchronize()
        self._compare(expected)
        # A second action proves capture did not freeze the original token values.
        self._copy_action(encode_controller_step(dict(durationMs=50,keys=['W'],mouseDx=37,mouseDy=-4)))
        expected=self._forward()
        self.graph.replay()
        torch.cuda.synchronize()
        self._compare(expected)
        self._copy_action(initial)
        self.validation=dict(enabled=True,captureValidated=True,parameterizedActionValidated=True,
                             priorCacheCopiedBeforeReplay=True)

    def _copy_action(self, encoded):
        """Transfer eight validated integer tokens once, with no asynchronous host-buffer reuse."""
        values=encoded['keys']+encoded['mouseButtons']+[encoded['mouseDxBin'],encoded['mouseDyBin']]
        self.action_values.copy_(torch.tensor(values,dtype=torch.int64,device='cpu'))

    def _forward(self):
        """Replay all visual, text and action embeddings through the full temporal pass."""
        with torch.inference_mode(),torch.device('cuda'),torch.autocast('cuda',dtype=self.dtype,
                                                                      enabled=self.dtype!=torch.float32):
            return teacher_forced_step(self.model,self.frame,self.index,self.state,self.text,None,
                                       action_tensors=self.action)

    def _compare(self, expected):
        """Match the eager selected-action pass before this graph can become usable."""
        torch.testing.assert_close(self.result[0],expected[0],rtol=0,atol=0)
        if len(self.result[1])!=len(expected[1]):raise AssertionError('Executed-history layer count changed')
        for actual,reference in zip(self.result[1],expected[1]):
            torch.testing.assert_close(actual.k_cache,reference.k_cache,rtol=1e-3,atol=1e-3)
            torch.testing.assert_close(actual.v_cache,reference.v_cache,rtol=1e-3,atol=1e-3)

    def replay(self, index, state, encoded):
        """Use the exact pre-prediction cache; never roll the sampled candidate forward again."""
        if len(state)!=len(self.state):raise ValueError('Executed-history prior layer count changed')
        self.index.copy_(index)
        for target,source in zip(self.state,state):
            target.k_cache.copy_(source.k_cache)
            target.v_cache.copy_(source.v_cache)
        self._copy_action(encoded)
        self.graph.replay()
        return self.result
