# MOSS-TTS-Nano CPU Gate — 2026-08-06

## Test setup

- Repository: `OpenMOSS/MOSS-TTS-Nano` at commit `cc7bdf1`
- Backend: native ONNX Runtime CPU
- CPU threads: `8`
- Reference: `chatterbox/voices/airi-reference.wav`
- Korean text: `안녕하세요. 오늘은 어떤 이야기를 해볼까요?`
- Streaming decode: enabled
- WeTextProcessing: disabled for the Korean-path test

## Result

Voice cloning and Korean synthesis completed successfully, but the realtime gate failed:

- Audio duration: `4.320 s`
- Wall time after model assets were present: `20.248 s`
- RTF: `4.687` (target is `< 1`)
- Output: `external/MOSS-TTS-Nano/generated_audio/moss-gate.wav`

The result is useful as a CPU/V-RAM-free fallback experiment, but it is not suitable for the current realtime conversation target on this PC. GPT-SoVITS v2ProPlus GPU remains the active TTS path.

Reproduce with:

```powershell
$py = 'C:\Projects\airi\external\GPT-SoVITS\.venv\Scripts\python.exe'
& $py C:\Projects\airi\gpt-sovits\benchmark-moss-onnx.py --threads 8
```
