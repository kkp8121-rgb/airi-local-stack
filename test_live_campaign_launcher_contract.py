from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WRAPPER = (ROOT / "run-airi-live-broadcast-campaign.ps1").read_text(encoding="utf-8")
TTS_START = (ROOT / "gpt-sovits" / "start-local-stack.ps1").read_text(encoding="utf-8")
LATENCY_START = (ROOT / "latency-monitor" / "start-latency-monitor.ps1").read_text(encoding="utf-8")


class LiveCampaignLauncherContractTests(unittest.TestCase):
    def test_wrapper_uses_fresh_isolated_local_services(self) -> None:
        self.assertIn("OutputDir must not already exist", WRAPPER)
        for port in (11435, 11436, 8880, 9880, 8892, 8890):
            self.assertIn(str(port), WRAPPER)
        self.assertIn("-MemoryDbPath $memoryDb", WRAPPER)
        self.assertIn("-KnowledgeDbPath $knowledgeDb", WRAPPER)
        self.assertIn("knowledge_ingest.py", WRAPPER)
        self.assertIn("airi_live_campaign_knowledge_fixture.json", WRAPPER)

    def test_cleanup_stops_only_exact_campaign_listener_pids(self) -> None:
        self.assertIn("Get-AiriCampaignOwnedServicePids", WRAPPER)
        self.assertIn("Stop-AiriCampaignOwnedServices", WRAPPER)
        self.assertIn("OwningProcess -eq $expectedPid", WRAPPER)
        self.assertIn("Get-Process -Id $expectedPid", WRAPPER)
        self.assertIn("Stop-Process -Id $expectedPid", WRAPPER)
        self.assertNotIn("stop-airi-local-stack.ps1", WRAPPER)
        self.assertIn("Get-AiriCampaignPartialServicePids", WRAPPER)
        self.assertIn("StartedAfterUtc", WRAPPER)
        self.assertIn("ollama-proxy\\ollama_proxy.py", WRAPPER)
        self.assertIn("gpt-sovits\\openai_compatible_proxy.py", WRAPPER)
        self.assertIn("gpt-sovits\\run_v2proplus_with_sv_cache.py", WRAPPER)
        self.assertIn("latency-monitor\\monitor_server.py", WRAPPER)
        self.assertIn("Get-CimInstance Win32_Process", WRAPPER)
        self.assertIn("$verifiedWithoutListener", WRAPPER)
        self.assertIn("-IdentityVerifiedOwners $partialOwners", WRAPPER)
        self.assertIn("$monitorServer = [IO.Path]::GetFullPath", LATENCY_START)
        self.assertIn("-ArgumentList $monitorServer", LATENCY_START)

    def test_capabilities_are_in_memory_distinct_and_restored(self) -> None:
        self.assertGreaterEqual(WRAPPER.count("New-AiriCampaignCapability"), 3)
        self.assertIn("$master -ceq $observer", WRAPPER)
        self.assertIn("LiveBroadcastMasterTokenOverride $master", WRAPPER)
        self.assertIn("LiveBroadcastObserverTokenOverride $observer", WRAPPER)
        self.assertIn("Restore-AiriEnvironmentValue 'AIRI_LIVE_BROADCAST_MASTER_TOKEN'", WRAPPER)
        self.assertNotIn("Write-Output $master", WRAPPER)
        self.assertNotIn("Write-Output $observer", WRAPPER)

    def test_full_stack_flags_stay_local_and_extraction_off(self) -> None:
        for contract in (
            "-EnableMemoryExtraction $false", "-AllowExternalMemoryExtraction $false",
            "-AllowExternalChat $false", "-AllowExternalSearch $false", "-Stt off",
            "-OutputModeration on", "-InputScreening on", "-EpistemicConfidence on",
            "-AffectContinuity on", "-LiveBroadcastEvalClock",
        ):
            self.assertIn(contract, WRAPPER)
        self.assertIn("AIRI_IMMEDIATE_ACK = 'marker'", WRAPPER)
        self.assertIn("AIRI_GPT_SOVITS_SV_CACHE = 'on'", WRAPPER)
        self.assertIn("GPT_SOVITS_STREAMING_MODE = '2'", WRAPPER)
        self.assertIn("$previousMinChunkLength", WRAPPER)
        self.assertIn("GPT_SOVITS_MIN_CHUNK_LENGTH = '16'", WRAPPER)
        self.assertIn("Restore-AiriEnvironmentValue 'GPT_SOVITS_STREAMING_MODE'", WRAPPER)
        self.assertIn("Restore-AiriEnvironmentValue 'GPT_SOVITS_MIN_CHUNK_LENGTH'", WRAPPER)

    def test_tts_launcher_fail_closes_overlay_reuse_and_runs_guarded_wrapper(self) -> None:
        self.assertIn("ReferenceEmbeddingCache on requires a fresh 9880 backend", TTS_START)
        self.assertIn("run_v2proplus_with_sv_cache.py", TTS_START)
        self.assertIn("--external-root", TTS_START)


if __name__ == "__main__":
    unittest.main()
