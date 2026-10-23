using Microsoft.Win32.SafeHandles;
using System;
using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;

namespace BetterGenshinImpact.Core.Pipes;

/// <summary>Same-user, local-only pipe creation shared by the restricted control and agent transports.</summary>
public static class LocalUserPipe
{
    /// <summary>Create a one-client pipe that allows medium-integrity tools to reach an elevated BetterGI process.</summary>
    public static NamedPipeServerStream Create(string pipeName, SecurityIdentifier userSid, int bufferSize = 65536)
    {
        var security = new PipeSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(userSid);
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.NetworkSid, null),
            PipeAccessRights.FullControl,
            AccessControlType.Deny));
        security.AddAccessRule(new PipeAccessRule(userSid, PipeAccessRights.FullControl, AccessControlType.Allow));
        var pipe = NamedPipeServerStreamAcl.Create(pipeName, PipeDirection.InOut, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.WriteThrough,
            bufferSize, bufferSize, security, additionalAccessRights: PipeAccessRights.TakeOwnership);
        try
        {
            // CreateNamedPipe with a SACL requires ACCESS_SYSTEM_SECURITY / SeSecurityPrivilege.
            // LABEL_SECURITY_INFORMATION is narrower: set only the mandatory label after
            // creation using the pipe handle's WRITE_OWNER right. This lowers only this
            // pipe object to medium integrity while preserving its same-user DACL.
            SetMediumMandatoryLabel(pipe.SafePipeHandle);
            return pipe;
        }
        catch
        {
            pipe.Dispose();
            throw;
        }
    }

    /// <summary>Set only the mandatory integrity label; the owner and network-deny access rules remain intact.</summary>
    private static void SetMediumMandatoryLabel(SafePipeHandle pipeHandle)
    {
        var descriptor = new RawSecurityDescriptor("S:(ML;;NW;;;ME)");
        var binary = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(binary, 0);
        var saclOffset = BitConverter.ToInt32(binary, 12);
        if (saclOffset <= 0 || saclOffset >= binary.Length)
            throw new InvalidOperationException("Could not build the pipe's medium-integrity label.");
        var descriptorMemory = Marshal.AllocHGlobal(binary.Length);
        try
        {
            Marshal.Copy(binary, 0, descriptorMemory, binary.Length);
            var error = NativeSecurityApi.SetSecurityInfo(pipeHandle, NativeSecurityApi.SeKernelObject,
                NativeSecurityApi.LabelSecurityInformation, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero,
                IntPtr.Add(descriptorMemory, saclOffset));
            if (error != 0)
                throw new Win32Exception(unchecked((int)error), "Could not set the named pipe's medium-integrity label.");
        }
        finally { Marshal.FreeHGlobal(descriptorMemory); }
    }

    /// <summary>Minimal Windows security API used solely for the pipe's mandatory label.</summary>
    private static class NativeSecurityApi
    {
        /// <summary>Kernel object security type.</summary>
        internal const int SeKernelObject = 6;
        /// <summary>Modify integrity labels without requesting the rest of the SACL.</summary>
        internal const uint LabelSecurityInformation = 0x00000010;
        /// <summary>Apply security information to this pipe handle.</summary>
        [DllImport("advapi32.dll", SetLastError = true)]
        internal static extern uint SetSecurityInfo(SafePipeHandle handle, int objectType, uint securityInfo,
            IntPtr owner, IntPtr group, IntPtr dacl, IntPtr sacl);
    }
}
