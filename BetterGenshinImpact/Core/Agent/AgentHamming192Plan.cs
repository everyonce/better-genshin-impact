// Managed port of fast_image_resize 5.1.4 Interpolation(Hamming), commit f368232463e1129f84688139a9cd39d6375c4b15.
// Copyright (c) 2021 Kirill Kuzminykh; upstream license retained in FIR-Hamming-LICENSE.txt.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Immutable coefficients for one source geometry and fixed packed RGB192 output.</summary>
/// <remarks>The caller caches this plan. Each caller owns its separate destination buffer;
/// the source is borrowed read-only during the call. No scratch image or native memory is needed.</remarks>
internal sealed class AgentHamming192Plan
{
    /// <summary>Fixed square policy input dimension.</summary>
    public const int OutputSize = 192;

    /// <summary>Exact RGB payload byte count written into the caller-owned destination.</summary>
    public const int OutputBytes = OutputSize * OutputSize * 3;

    /// <summary>Explicit supported bound; dimensions outside this range are unsupported.</summary>
    public const int MaximumSourceDimension = 8192;

    /// <summary>Immutable source geometry and per-axis normalization precision.</summary>
    private readonly int _width, _height, _xPrecision, _yPrecision;

    /// <summary>Immutable normalized integer kernels, never exposed by reference.</summary>
    private readonly Kernel[] _columns, _rows;

    /// <summary>A nonadaptive support-one Hamming kernel has exactly one or two nonzero taps.</summary>
    /// <param name="Start">First source pixel index.</param>
    /// <param name="Count">Number of nonzero taps.</param>
    /// <param name="Weight0">First normalized i16 coefficient.</param>
    /// <param name="Weight1">Second coefficient, or zero for a one-tap kernel.</param>
    private readonly record struct Kernel(int Start, int Count, short Weight0, short Weight1);

    /// <summary>Source dimensions used to select/reuse this immutable plan.</summary>
    public int Width => _width;
    /// <summary>Source height used to select/reuse this immutable plan.</summary>
    public int Height => _height;

    /// <summary>Compute coefficients once; the resulting plan is safe for concurrent read-only reuse.</summary>
    public AgentHamming192Plan(int width, int height)
    {
        ValidateDimension(width, nameof(width));
        ValidateDimension(height, nameof(height));
        _width = width;
        _height = height;
        (_xPrecision, _columns) = BuildAxis(width);
        (_yPrecision, _rows) = BuildAxis(height);
    }

    /// <summary>Convert borrowed native rows into the caller-owned, tightly packed RGB192 destination prefix.</summary>
    /// <remarks>Positive stride only. Last-row padding need not be present. Alpha is ignored.
    /// Vertical results are rounded/clipped to U8 before horizontal multiplication, matching FIR.
    /// Computing only the vertical pixels consumed by each horizontal tap avoids scratch storage.</remarks>
    public void ResizeInto(ReadOnlySpan<byte> source, int stride, int channels, bool blueFirst, Span<byte> output)
    {
        if (channels is not (3 or 4))
            throw new ArgumentOutOfRangeException(nameof(channels), "Only RGB/BGR/RGBA/BGRA are supported.");
        int rowBytes = checked(_width * channels);
        if (stride < rowBytes)
            throw new ArgumentOutOfRangeException(nameof(stride), "Stride must be positive and contain a full row.");
        long requiredBytes = checked((long)(_height - 1) * stride + rowBytes);
        if (requiredBytes > int.MaxValue)
            throw new ArgumentOutOfRangeException(nameof(stride), "Source row offsets exceed managed span bounds.");
        if (source.Length < requiredBytes)
            throw new ArgumentException("The source does not contain every visible row.", nameof(source));

        if (output.Length < OutputBytes)
            throw new ArgumentException("The destination cannot contain the RGB192 payload.", nameof(output));
        if (source.Overlaps(output))
            throw new ArgumentException("Source and destination ownership must not overlap.", nameof(output));

        // No per-frame allocation or retained buffer: only the exact payload prefix is written.
        int xBias = 1 << (_xPrecision - 1), yBias = 1 << (_yPrecision - 1);
        for (int y = 0; y < OutputSize; y++)
        {
            Kernel ky = _rows[y];
            int row0 = ky.Start * stride;
            int row1 = ky.Count == 2 ? (ky.Start + 1) * stride : row0;
            for (int x = 0; x < OutputSize; x++)
            {
                Kernel kx = _columns[x];
                int pixel0 = row0 + kx.Start * channels;
                int pixel1 = row1 + kx.Start * channels;
                int destination = (y * OutputSize + x) * 3;
                for (int channel = 0; channel < 3; channel++)
                {
                    int c = blueFirst ? 2 - channel : channel;
                    int vertical = yBias + source[pixel0 + c] * ky.Weight0;
                    if (ky.Count == 2) vertical += source[pixel1 + c] * ky.Weight1;
                    int horizontal = xBias + RoundedByte(vertical, _yPrecision) * kx.Weight0;
                    if (kx.Count == 2)
                    {
                        vertical = yBias + source[pixel0 + channels + c] * ky.Weight0;
                        if (ky.Count == 2) vertical += source[pixel1 + channels + c] * ky.Weight1;
                        horizontal += RoundedByte(vertical, _yPrecision) * kx.Weight1;
                    }
                    output[destination + channel] = RoundedByte(horizontal, _xPrecision);
                }
            }
        }
    }

    /// <summary>Export precision followed by start/count/weight0/weight1 tuples for oracle validation.</summary>
    internal int[] ExportAxisForValidation(bool horizontal)
    {
        Kernel[] kernels = horizontal ? _columns : _rows;
        var result = new int[1 + OutputSize * 4];
        result[0] = horizontal ? _xPrecision : _yPrecision;
        for (int i = 0; i < kernels.Length; i++)
        {
            Kernel kernel = kernels[i];
            result[1 + i * 4] = kernel.Start;
            result[2 + i * 4] = kernel.Count;
            result[3 + i * 4] = kernel.Weight0;
            result[4 + i * 4] = kernel.Weight1;
        }
        return result;
    }

    /// <summary>Validate before any dimension arithmetic, allocation or source access.</summary>
    private static void ValidateDimension(int value, string parameter)
    {
        if (value < 1 || value > MaximumSourceDimension)
            throw new ArgumentOutOfRangeException(parameter, "Supported dimensions are 1 through 8192.");
    }

    /// <summary>Apply each U8 pass's positive half-unit bias, arithmetic shift and saturation.</summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static byte RoundedByte(int biasedValue, int precision) =>
        (byte)Math.Clamp(biasedValue >> precision, 0, 255);

    /// <summary>Build the pinned full-frame, nonadaptive support-one filter and Normalizer16 coefficients.</summary>
    private static (int Precision, Kernel[] Kernels) BuildAxis(int input)
    {
        var raw = new (int Start, double[] Weights)[OutputSize];
        double scale = (double)input / OutputSize, maximum = 0;
        for (int output = 0; output < OutputSize; output++)
        {
            double inCenter = (output + 0.5) * scale;
            int lower = Math.Max(0, (int)Math.Floor(inCenter - 1));
            int upper = Math.Min(input, (int)Math.Ceiling(inCenter + 1));
            int start = lower;
            var weights = new List<double>(3);
            double sum = 0;
            for (int source = lower; source < upper; source++)
            {
                double weight = Hamming(source - (inCenter - 0.5));
                if (source == start && weight == 0) start++;
                else { weights.Add(weight); sum += weight; }
            }
            while (weights.Count > 0 && weights[^1] == 0) weights.RemoveAt(weights.Count - 1);
            if (weights.Count is < 1 or > 2 || !double.IsFinite(sum) || sum <= 0)
                throw new InvalidOperationException("Unexpected Hamming support or normalization.");
            for (int i = 0; i < weights.Count; i++)
            {
                weights[i] /= sum;
                maximum = Math.Max(maximum, weights[i]);
            }
            raw[output] = (start, weights.ToArray());
        }

        // Rust f64::round is ties away from zero; .NET's default ties-to-even is not equivalent.
        int precision = 0;
        for (int candidate = 0; candidate < 22; candidate++)
        {
            precision = candidate;
            if (Math.Round(maximum * (1 << (precision + 1)), MidpointRounding.AwayFromZero) >= 32768) break;
        }
        var kernels = new Kernel[OutputSize];
        for (int i = 0; i < raw.Length; i++)
        {
            var (start, weights) = raw[i];
            short first = checked((short)Math.Round(weights[0] * (1 << precision), MidpointRounding.AwayFromZero));
            short second = weights.Length == 2
                ? checked((short)Math.Round(weights[1] * (1 << precision), MidpointRounding.AwayFromZero)) : (short)0;
            kernels[i] = new Kernel(start, weights.Length, first, second);
        }
        return (precision, kernels);
    }

    /// <summary>Evaluate the exact upstream Hamming expression in double precision.</summary>
    private static double Hamming(double distance)
    {
        distance = Math.Abs(distance);
        if (distance == 0) return 1;
        if (distance >= 1) return 0;
        double radians = distance * Math.PI;
        return (0.54 + 0.46 * Math.Cos(radians)) * Math.Sin(radians) / radians;
    }
}
