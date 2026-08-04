#!/bin/bash
# Benchmark Qwen3-TTS with CUDA Graphs.
# Usage: ./benchmark.sh [0.6B|1.7B|both|custom|backends|backend-base]
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

MODEL="${1:-both}"
PY="$DIR/.venv/bin/python"

if [ ! -f "$PY" ]; then
    echo "ERROR: venv not found. Run ./setup.sh first."
    exit 1
fi

$PY -c "import torch; assert torch.cuda.is_available()" 2>/dev/null || {
    echo "ERROR: PyTorch with CUDA required. Check your venv."
    exit 1
}

GPU_NAME=$($PY -c 'import torch; print(torch.cuda.get_device_name(0))')
echo "=== Faster Qwen3-TTS Benchmark ==="
echo "GPU: $GPU_NAME"
echo "PyTorch: $($PY -c 'import torch; print(torch.__version__)')"
echo "CUDA: $($PY -c 'import torch; print(torch.version.cuda)')"
echo ""

run_model() {
    local size=$1
    echo "--- Benchmarking $size ---"
    MODEL_SIZE="$size" $PY "$DIR/benchmarks/throughput.py"
    echo ""
}

run_custom() {
    local size=$1
    echo "--- Benchmarking $size (CustomVoice) ---"
    MODEL_SIZE="$size" $PY "$DIR/benchmarks/custom_voice.py"
    echo ""
}

run_backend_compare() {
    local size="${1:-1.7B}"
    local mode="${2:-custom}"
    local args=(
        --backend both
        --mode "$mode"
        --model-size "$size"
        --quant "${QUANT:-BF16}"
        --greedy
    )

    if [ "${LOCAL_FILES_ONLY:-1}" != "0" ]; then
        args+=(--local-files-only)
    fi

    if [ -n "${QWENTTS_LIB:-}" ]; then
        args+=(--qwentts-lib "$QWENTTS_LIB")
    fi

    echo "--- Comparing Torch and GGML ($size, $mode) ---"
    "$PY" "$DIR/benchmarks/backend_compare.py" "${args[@]}"
    echo ""
}

case "$MODEL" in
    0.6B) run_model "0.6B" ;;
    1.7B) run_model "1.7B" ;;
    custom)
        run_custom "0.6B"
        run_custom "1.7B"
        ;;
    both)
        run_model "0.6B"
        run_model "1.7B"
        ;;
    backends)
        run_backend_compare "${MODEL_SIZE:-1.7B}" "${MODE:-custom}"
        ;;
    backend-base)
        run_backend_compare "${MODEL_SIZE:-0.6B}" "base"
        ;;
    *)
        echo "Usage: ./benchmark.sh [0.6B|1.7B|both|custom|backends|backend-base]"
        echo ""
        echo "Backend comparison options:"
        echo "  MODEL_SIZE=1.7B MODE=custom QUANT=BF16 ./benchmark.sh backends"
        echo "  MODEL_SIZE=0.6B QUANT=BF16 ./benchmark.sh backend-base"
        echo "  QWENTTS_LIB=/path/to/libqwen.so ./benchmark.sh backends"
        exit 1
        ;;
esac

echo "Done. Results saved as bench_results_*.json"
