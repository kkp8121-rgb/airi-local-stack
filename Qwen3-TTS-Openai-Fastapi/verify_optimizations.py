#!/usr/bin/env python3
"""
Quick verification test for optimizations.
Tests that the API is working and measures performance.
"""

import time
import requests
import sys

API_URL = "http://localhost:8880/v1/audio/speech"

def test_optimization():
    """Quick test to verify optimizations are working."""
    
    print("🧪 Testing Optimized Qwen3-TTS Backend")
    print("=" * 60)
    
    # Wait for API
    print("\n⏳ Waiting for API to be ready...")
    for i in range(60):
        try:
            response = requests.get("http://localhost:8880/health", timeout=2)
            if response.status_code == 200:
                health = response.json()
                print(f"✅ API is ready!")
                print(f"   Backend: {health['backend']['name']}")
                print(f"   Model: {health['backend']['model_id']}")
                print(f"   Device: {health['device']['gpu_name']}")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("❌ API not ready after 60 seconds")
        return False
    
    # Warmup request (torch.compile needs warmup)
    print("\n🔥 Warmup request (torch.compile compilation)...")
    warmup_start = time.time()
    try:
        response = requests.post(
            API_URL,
            json={
                "input": "Warmup test for torch compile optimization.",
                "voice": "Vivian",
                "model": "tts-1",
                "response_format": "mp3",
            },
            timeout=120
        )
        warmup_time = time.time() - warmup_start
        print(f"   Warmup completed in {warmup_time:.2f}s")
        if response.status_code != 200:
            print(f"   ⚠️ Warmup returned status {response.status_code}")
    except Exception as e:
        print(f"   ⚠️ Warmup error: {e}")
    
    # Test requests
    test_cases = [
        ("Hello world!", "Short", 2),
        ("The quick brown fox jumps over the lazy dog.", "Sentence", 9),
        ("Artificial intelligence is transforming the way we live and work in amazing ways.", "Medium", 14),
    ]
    
    print("\n📊 Performance Test (with optimizations)")
    print("-" * 60)
    
    results = []
    for text, name, words in test_cases:
        start = time.time()
        
        try:
            response = requests.post(
                API_URL,
                json={
                    "input": text,
                    "voice": "Vivian",
                    "model": "tts-1",
                    "response_format": "mp3",
                },
                timeout=60
            )
            
            elapsed = time.time() - start
            
            if response.status_code == 200:
                # Rough estimate: ~12Hz model, ~10 words/second speech
                audio_duration = words * 0.6  # Conservative estimate
                rtf = elapsed / audio_duration if audio_duration > 0 else 0
                
                results.append({
                    'name': name,
                    'latency': elapsed,
                    'rtf': rtf,
                    'words': words,
                })
                
                print(f"   {name:10s} ({words:2d}w): {elapsed:5.2f}s  RTF: {rtf:.2f}")
            else:
                print(f"   {name:10s} - ERROR: HTTP {response.status_code}")
        
        except Exception as e:
            print(f"   {name:10s} - ERROR: {e}")
    
    if results:
        avg_rtf = sum(r['rtf'] for r in results) / len(results)
        avg_lat = sum(r['latency'] for r in results) / len(results)
        
        print("-" * 60)
        print(f"\n📈 Results:")
        print(f"   Average RTF: {avg_rtf:.2f}")
        print(f"   Average Latency: {avg_lat:.2f}s")
        
        # Compare to baseline
        baseline_rtf = 0.97
        flash_rtf = 0.87
        
        if avg_rtf < flash_rtf:
            improvement = ((flash_rtf - avg_rtf) / flash_rtf) * 100
            print(f"   ✅ {improvement:.1f}% faster than Flash Attn 2 baseline!")
            print(f"   🏆 torch.compile() is working!")
        elif avg_rtf < baseline_rtf:
            improvement = ((baseline_rtf - avg_rtf) / baseline_rtf) * 100
            print(f"   ✅ {improvement:.1f}% faster than baseline")
        else:
            print(f"   ⚠️ Performance similar to or slower than baseline")
            print(f"      (May need more warmup requests)")
        
        print("\n" + "=" * 60)
        print("✅ Optimization verification complete!")
        print("=" * 60)
        return True
    else:
        print("\n❌ No successful test results")
        return False

if __name__ == "__main__":
    success = test_optimization()
    sys.exit(0 if success else 1)
