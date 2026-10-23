"""Profile one GameScaling action after warmup; profiler timings are diagnostic."""
import argparse
import json
from pathlib import Path
import torch
from PIL import Image
from model_adapters import GameScalingAdapter


def main():
    """Save operator costs separately from ordinary uninstrumented benchmarks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cuda-graph', action='store_true')
    args = parser.parse_args()
    policy = GameScalingAdapter(args.checkpoint, args.source, max_new_tokens=48,
                                cuda_graph=args.cuda_graph)
    image = Image.open(args.image).convert('RGB')
    policy.predict(image, image.size)
    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,
                                          torch.profiler.ProfilerActivity.CUDA]) as profile:
        result = policy.predict(image, image.size)
    operators = [{'name': event.key, 'calls': event.count,
                  'selfCpuUs': event.self_cpu_time_total,
                  'selfDeviceUs': event.self_device_time_total}
                 for event in profile.key_averages()]
    operators.sort(key=lambda event: event['selfDeviceUs'], reverse=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'scope': 'Instrumented diagnostic, not a latency benchmark',
                                 'arguments': vars(args), 'adapter': policy.metadata,
                                 'result': result, 'operators': operators}, indent=2), encoding='utf-8')
    print(json.dumps(operators[:15], indent=2))


if __name__ == '__main__':
    main()
