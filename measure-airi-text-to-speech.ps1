[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$Text,
  [string]$SourceRoot = $(if ($env:AIRI_SOURCE_ROOT) { $env:AIRI_SOURCE_ROOT } else { Join-Path $env:TEMP 'airi-v0113-source-codex-20260808' }),
  [string]$SenderScript,
  [ValidateRange(0.000001, 1.0)]
  [double]$Threshold = 0.01,
  [Alias('Timeout')]
  [ValidateRange(1, 600)]
  [int]$TimeoutSeconds = 90,
  [ValidateRange(10, 20)]
  [int]$SampleIntervalMs = 15,
  [ValidateRange(0, 2000)]
  [int]$GapMergeMs = 120,
  [ValidateRange(0, 10000)]
  [int]$MinDurationMs = 25,
  [ValidateRange(0, 10000)]
  [int]$PostPlaybackMs = 6000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This is deliberately an endpoint meter only.  It neither opens a capture
# endpoint nor saves audio, microphone, speech-to-text, session IDs, or text.
if (-not ('AiriDefaultRenderMeter' -as [type])) {
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public enum EDataFlow { eRender = 0, eCapture = 1, eAll = 2 }
public enum ERole { eConsole = 0, eMultimedia = 1, eCommunications = 2 }

[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
  int EnumAudioEndpoints(EDataFlow dataFlow, int stateMask, out object devices);
  int GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role, out IMMDevice endpoint);
  int GetDevice(string id, out IMMDevice device);
  int RegisterEndpointNotificationCallback(IntPtr client);
  int UnregisterEndpointNotificationCallback(IntPtr client);
}

[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
  int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object audioClient);
  int OpenPropertyStore(int stgmAccess, out object properties);
  int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
  int GetState(out int state);
}

[ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioMeterInformation {
  int GetPeakValue(out float peak);
  int GetMeteringChannelCount(out int channelCount);
  int GetChannelsPeakValues(int channelCount, out IntPtr peakValues);
  int QueryHardwareSupport(out int hardwareSupportMask);
  int GetHardwareSupportMask(out int hardwareSupportMask);
}

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumeratorComObject { }

public sealed class AiriDefaultRenderMeter : IDisposable {
  private object enumerator;
  private object device;
  private IAudioMeterInformation meter;
  public AiriDefaultRenderMeter() {
    enumerator = new MMDeviceEnumeratorComObject();
    IMMDevice endpoint;
    Marshal.ThrowExceptionForHR(((IMMDeviceEnumerator)enumerator).GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia, out endpoint));
    device = endpoint;
    Guid meterIid = typeof(IAudioMeterInformation).GUID;
    object activated;
    Marshal.ThrowExceptionForHR(endpoint.Activate(ref meterIid, 23, IntPtr.Zero, out activated));
    meter = (IAudioMeterInformation)activated;
  }
  public float Peak() {
    float peak;
    Marshal.ThrowExceptionForHR(meter.GetPeakValue(out peak));
    return peak;
  }
  public void Dispose() {
    if (meter != null) { Marshal.FinalReleaseComObject(meter); meter = null; }
    if (device != null && Marshal.IsComObject(device)) { Marshal.FinalReleaseComObject(device); device = null; }
    if (enumerator != null && Marshal.IsComObject(enumerator)) { Marshal.FinalReleaseComObject(enumerator); enumerator = null; }
  }
}
'@
}

if (-not $SenderScript) { $SenderScript = Join-Path $PSScriptRoot 'send-airi-local-text.mjs' }
$SenderScript = [IO.Path]::GetFullPath($SenderScript)
$SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
$node = (Get-Command node -CommandType Application | Select-Object -First 1 -ExpandProperty Source)
$textBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
$charCount = 0
for ($index = 0; $index -lt $Text.Length; $index++) {
  $charCount++
  if ([char]::IsHighSurrogate($Text[$index]) -and $index + 1 -lt $Text.Length -and [char]::IsLowSurrogate($Text[$index + 1])) {
    $index++
  }
}

$process = $null
$meter = $null
try {
  # Open the render meter before starting the sender so an immediate ACK is
  # observable as well as the later substantive response.
  $meter = [AiriDefaultRenderMeter]::new()
  $psi = [Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $node
  $psi.Arguments = ('"{0}" --text-base64 {1} --wait-complete --wait-playback-start --print-wall-clock-timing' -f $SenderScript, $textBase64)
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $psi.EnvironmentVariables['AIRI_SOURCE_ROOT'] = $SourceRoot
  $process = [Diagnostics.Process]::new()
  $process.StartInfo = $psi
  if (-not $process.Start()) { throw 'sender_start_failed' }
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()
  $regions = [Collections.Generic.List[object]]::new()
  $active = $null
  $deadline = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + ($TimeoutSeconds * 1000)
  $tailUntil = $null
  while ($true) {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    if ($now -gt $deadline) { throw 'timeout' }
    $peak = [double]$meter.Peak()
    if ($peak -ge $Threshold) {
      if ($null -eq $active) {
        $active = [ordered]@{ start_epoch_ms = $now; end_epoch_ms = $now; peak = $peak }
      } else {
        $active.end_epoch_ms = $now
        if ($peak -gt $active.peak) { $active.peak = $peak }
      }
    } elseif ($null -ne $active -and ($now - $active.end_epoch_ms) -gt $GapMergeMs) {
      if (($active.end_epoch_ms - $active.start_epoch_ms) -ge $MinDurationMs) { [void]$regions.Add([pscustomobject]$active) }
      $active = $null
    }
    if ($process.HasExited) {
      if ($null -eq $tailUntil) { $tailUntil = $now + $PostPlaybackMs }
      if ($now -ge $tailUntil) { break }
    }
    Start-Sleep -Milliseconds $SampleIntervalMs
  }
  if ($null -ne $active -and ($active.end_epoch_ms - $active.start_epoch_ms) -ge $MinDurationMs) { [void]$regions.Add([pscustomobject]$active) }
  $sender = $stdoutTask.GetAwaiter().GetResult() | ConvertFrom-Json
  [void]$stderrTask.GetAwaiter().GetResult() # drain only; never report its content
  if ($process.ExitCode -ne 0 -or -not $sender.sent -or -not $sender.completed -or -not $sender.playback_started -or $null -eq $sender.sent_epoch_ms) { throw 'sender_did_not_complete_with_playback_start' }
  $sentEpochMs = [int64]$sender.sent_epoch_ms
  $relativeRegions = @($regions | Where-Object { $_.end_epoch_ms -ge $sentEpochMs } | ForEach-Object {
    [pscustomobject][ordered]@{
      start_ms = [math]::Max(0, [int64]$_.start_epoch_ms - $sentEpochMs)
      end_ms = [math]::Max(0, [int64]$_.end_epoch_ms - $sentEpochMs)
      peak = $_.peak
    }
  })
  $firstPostCompletion = $relativeRegions |
    Where-Object { $_.start_ms -ge [int64]$sender.completed_ms } |
    Select-Object -First 1 -ExpandProperty start_ms
  $result = [ordered]@{
    ok = $true
    chars = $charCount
    sent_epoch_ms = $sentEpochMs
    completed_ms = [int64]$sender.completed_ms
    playback_started_ms = [int64]$sender.playback_started_ms
    playback_started_epoch_ms = $sentEpochMs + [int64]$sender.playback_started_ms
    threshold = $Threshold
    sample_interval_ms = $SampleIntervalMs
    gap_merge_ms = $GapMergeMs
    min_duration_ms = $MinDurationMs
    first_region_after_completion_ms = $firstPostCompletion
    peak_regions = $relativeRegions
  }
  $result | ConvertTo-Json -Compress -Depth 4
}
catch {
  # Do not propagate sender output, input text, or endpoint/session identifiers.
  [ordered]@{ ok = $false; chars = $charCount; error = 'measurement_failed' } | ConvertTo-Json -Compress
  exit 1
}
finally {
  if ($process -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
  if ($meter) { $meter.Dispose() }
  if ($process) { $process.Dispose() }
}
