# Resume-Ops Evaluation & Observability Guide

`resume-ops` provides a multi-layered evaluation and observability framework designed to ensure high tailoring quality, strict anti-hallucination compliance, and real-time execution tracing.

---

## 1. Enabling & Disabling Tracing (Opik / Langfuse)

Tracing is **disabled by default** (`ENABLE_TRACING=false`). When disabled, `resume-ops` executes locally with zero external network overhead.

### How to Enable Tracing:
In your `.env` file or environment:

```bash
# Enable live tracing for LangGraph nodes and LiteLLM completions
ENABLE_TRACING=true
OPIK_API_KEY=your_opik_api_key
OPIK_PROJECT_NAME=resume-ops
```

Once enabled, every tailoring request sent to `POST /api/v1/tailor` automatically streams spans, token consumption, latency, and node states to your Opik project dashboard.

---

## 2. DeepEval Quality & Anti-Hallucination Testing

DeepEval provides Python-native evaluation metrics (`FaithfulnessMetric`, `HallucinationMetric`, `GEval`) that run directly inside `pytest`.

### Running Evaluation Tests:

```bash
# Fast unit tests (skips evaluation model runs)
pytest

# Run LLM quality evaluation tests
pytest -m eval
```

### Configuring Evaluation Model:
Evaluation tests use an LLM to judge output quality. You can route evaluation requests to your local model or cloud API by setting:

```bash
EVAL_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your_api_key
```

---

## 3. Promptfoo Prompt Regression Benchmarking

Promptfoo allows CLI matrix testing of prompt changes across multiple models and datasets before committing code.

### Running Promptfoo Benchmarks:

```bash
# Run benchmark matrix using promptfooconfig.yaml
npx promptfoo@latest eval

# View interactive benchmark report in browser
npx promptfoo@latest view
```

### Benchmark Checks:
- **Strict Immutability**: Ensures company names, start/end dates, and candidate identities remain unchanged.
- **JSON Schema Validation**: Verifies that responses comply with JSON Resume schema.
- **LLM Rubric Scoring**: Evaluates keyword alignment against job description requirements.
