using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;

// Hold exclusive ownership of the candidate through verification and disposition.
// A concurrent writer or loaded image makes the operation fail; no process is stopped.
public static class ApprovedFileCleanup
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string path, uint access, uint share,
        IntPtr security, uint creation, uint attributes, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetFileInformationByHandle(SafeFileHandle handle, int informationClass,
        ref Disposition disposition, uint size);
    [StructLayout(LayoutKind.Sequential)]
    private struct Disposition { [MarshalAs(UnmanagedType.Bool)] public bool Delete; }

    public static void DeleteVerified(string path, string preserved, string expectedHash, long expectedLength)
        => DeleteWithWitness(path, preserved, expectedHash, expectedLength, expectedHash, expectedLength);

    public static void DeleteWithWitness(string path, string preserved, string expectedHash, long expectedLength,
        string witnessHash, long witnessLength)
    {
        using var handle = CreateFile(path, 0x80000000 | 0x00010000, 0, IntPtr.Zero, 3, 0x80, IntPtr.Zero);
        if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "Candidate is locked or cannot be opened exclusively");
        using var candidate = new FileStream(handle, FileAccess.Read);
        using var retained = new FileStream(preserved, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (candidate.Length != expectedLength || retained.Length != witnessLength ||
            !Convert.ToHexString(SHA256.HashData(candidate)).Equals(expectedHash, StringComparison.OrdinalIgnoreCase) ||
            !Convert.ToHexString(SHA256.HashData(retained)).Equals(witnessHash, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Candidate or protected copy changed; nothing deleted");
        var disposition = new Disposition { Delete = true };
        if (!SetFileInformationByHandle(handle, 4, ref disposition, (uint)Marshal.SizeOf<Disposition>()))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Windows refused verified-file deletion");
    }
}
