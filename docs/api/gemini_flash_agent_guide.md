# Gemini API: Gemini 3 Flash + Gemini 2.5 Flash (agent cheat sheet)

This guide targets:
- **Gemini 3 Flash**: `gemini-3-flash-preview`
- **Gemini 2.5 Flash**: `gemini-2.5-flash`

---

## 0) Model selection (what to call)

**Gemini 3 Flash (Preview)**  
- Model code: `gemini-3-flash-preview`  
- Input token limit: 1,048,576; output token limit: 65,536  
- Supports: thinking, structured outputs, tools (function calling, code execution, file search, URL context, Google Search grounding), caching, Batch API  
- Does **not** support: Live API, image generation, audio generation

**Gemini 2.5 Flash (Stable)**  
- Model code: `gemini-2.5-flash`  
- Input token limit: 1,048,576; output token limit: 65,536  
- Supports: thinking, structured outputs, tools (function calling, code execution, URL context, Google Search grounding), caching, Batch API

---

## 1) Setup (SDK + API key)

### API key
Set an environment variable:
```bash
export GEMINI_API_KEY="YOUR_KEY"
```

### Install SDKs

**Python**
```bash
pip install -U google-genai
```

**Node (JS/TS)**
```bash
npm install @google/genai
```

---

## 2) Minimal “generate content” calls

### Python (text in → text out)
```python
import os
from google import genai

client = genai.Client()  # reads GEMINI_API_KEY from env

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Write a one-sentence summary of Gödel's incompleteness theorems."
)
print(resp.text)
```

### JavaScript (text in → text out)
```js
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({}); // reads GEMINI_API_KEY from env

const resp = await ai.models.generateContent({
  model: "gemini-3-flash-preview",
  contents: "Explain what a monoid is, in 2 sentences.",
});
console.log(resp.text);
```

### REST (curl)
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      { "parts": [ { "text": "Explain what a sigma-algebra is." } ] }
    ]
  }'
```

---

## 3) The main knobs (“config” / “generationConfig”)

In the **SDK**, you typically pass these under `config=...` (Python) or `config: {...}` (JS).  
In **REST**, most go inside `"generationConfig": {...}` plus some top-level fields like `systemInstruction`, `tools`, `toolConfig`, `safetySettings`.

### 3.1 Sampling / length / candidates
Common knobs (names vary slightly by SDK vs REST):
- `maxOutputTokens`
- `temperature`
- `topP`
- `topK`
- `candidateCount`
- `seed`
- `stopSequences`
- `presencePenalty`
- `frequencyPenalty`

**Example (JS):**
```js
const resp = await ai.models.generateContent({
  model: "gemini-2.5-flash",
  contents: "Generate 5 theorem names.",
  config: {
    maxOutputTokens: 256,
    temperature: 0.7,
    topP: 0.95,
    topK: 40,
    candidateCount: 1,
    seed: 1234,
    stopSequences: ["\n\n"],
  },
});
```

**Example (REST):**
```json
{
  "contents": [{ "parts": [{ "text": "Generate 5 theorem names." }] }],
  "generationConfig": {
    "maxOutputTokens": 256,
    "temperature": 0.7,
    "topP": 0.95,
    "topK": 40,
    "candidateCount": 1,
    "seed": 1234,
    "stopSequences": ["\n\n"]
  }
}
```

---

## 4) Thinking controls (and returning “thoughts”)

Thinking is controlled via `thinkingConfig`.

### 4.1 Returning a “thought summary” in the response
Set:
- `thinkingConfig.includeThoughts = true`

This adds “thought” parts to the model output (useful for debugging; do **not** treat as ground truth).

**Python**
```python
from google import genai
from google.genai import types

client = genai.Client()

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Solve: 1+...+n = ? (give closed form).",
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(include_thoughts=True)
    )
)
print(resp.candidates[0].content.parts)  # includes thought/text parts
```

### 4.2 Gemini 2.5 Flash: `thinkingBudget`
For 2.5 models, control “how much thinking” via:
- `thinkingConfig.thinkingBudget` (integer)

Typical patterns used in the docs:
- `thinkingBudget = 0` → disable thinking
- `thinkingBudget = -1` → “dynamic” thinking (model decides)

**REST**
```json
{
  "contents": [{ "parts": [{ "text": "Prove a simple lemma in Lean." }] }],
  "generationConfig": {
    "thinkingConfig": { "thinkingBudget": 256, "includeThoughts": true }
  }
}
```

### 4.3 Gemini 3 Flash: `thinkingLevel` (preferred)
For Gemini 3 models, use:
- `thinkingConfig.thinkingLevel` ∈ `{ "minimal", "low", "medium", "high" }`

Notes:
- For **Gemini 3 Flash**, docs state only `minimal` and `medium` are supported.
- Setting `thinkingLevel` on earlier models can error.

**JS**
```js
const resp = await ai.models.generateContent({
  model: "gemini-3-flash-preview",
  contents: "Explain why the harmonic series diverges.",
  config: {
    thinkingConfig: { thinkingLevel: "medium", includeThoughts: true },
  },
});
```

### 4.4 Gemini 3 “thought signatures” (important for tool loops)
Gemini 3 can emit a `thoughtSignature` that must be fed back in subsequent turns to preserve reasoning context.
- For **function calling**, the API can strictly validate that you returned the signatures (missing signatures can produce a 400 error).
- Official SDKs handle this automatically if you pass normal chat history back.

If you implement tool loops manually, make sure you **round-trip** the full returned parts (including signatures), not only `.text`.

---

## 5) Token log probabilities (“logprobs”)

Enable token-level log probabilities via `generationConfig`:
- `responseLogprobs: true`
- `logprobs: K` where `K ∈ [0, 20]` (top-K alternatives returned per decoding step)

Returned in:
- `candidates[0].avgLogprobs`
- `candidates[0].logprobsResult`, which includes:
  - `logProbabilitySum`
  - `chosenCandidates[]` (chosen token + logProbability each step)
  - `topCandidates[]` (top-K candidates each step)

### 5.1 REST example
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"parts":[{"text":"Give a Lean proof sketch for commutativity of addition on Nat."}]}],
    "generationConfig": {
      "responseLogprobs": true,
      "logprobs": 5,
      "maxOutputTokens": 512
    }
  }'
```

### 5.2 Python: read logprobs
```python
from google import genai
from google.genai import types

client = genai.Client()

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Output exactly: hello",
    config=types.GenerateContentConfig(
        generation_config=types.GenerationConfig(
            response_logprobs=True,
            logprobs=5,
            max_output_tokens=16,
        )
    )
)

cand = resp.candidates[0]
print("avgLogprobs:", cand.avg_logprobs)
print("sum:", cand.logprobs_result.log_probability_sum)
# cand.logprobs_result.chosen_candidates is a per-step list
```

---

## 6) System instruction / role messages

A “system instruction” steers behavior like a system prompt.

### Python
```python
from google import genai
from google.genai import types

client = genai.Client()

resp = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents="Hello there",
    config=types.GenerateContentConfig(
        system_instruction="You are a strict Lean 4 proof assistant. Output only Lean code."
    ),
)
print(resp.text)
```

### JS
```js
const resp = await ai.models.generateContent({
  model: "gemini-3-flash-preview",
  contents: "Hello there",
  config: { systemInstruction: "You are a strict Lean 4 proof assistant. Output only Lean code." },
});
```

---

## 7) Structured outputs (JSON mode + schema)

Two related knobs:
- `responseMimeType: "application/json"` (requests JSON output)
- `responseSchema` / `responseJsonSchema` (provide a JSON schema to enforce structure)

**Gemini 3 note:** Docs explicitly call out that “Structured outputs with tools” is a *Gemini 3 preview feature* for `gemini-3-*-preview`.

### JS (Gemini 3: schema via JSON schema)
```js
const resp = await ai.models.generateContent({
  model: "gemini-3-flash-preview",
  contents: "Return {name, years} for Gauss.",
  config: {
    responseMimeType: "application/json",
    responseJsonSchema: {
      type: "object",
      properties: {
        name: { type: "string" },
        years: { type: "string" }
      },
      required: ["name", "years"]
    }
  }
});
console.log(resp.text); // JSON string
```

---

## 8) Tools / function calling

### 8.1 Declaring functions
Provide `tools: [{ functionDeclarations: [...] }]`.

Then configure tool behavior using `toolConfig.functionCallingConfig.mode` (the docs show `auto` and `ANY` examples):
- `auto` (default / model decides)
- `ANY` (force the model to return a function call suggestion)

### Python (force a function call)
```python
from google import genai
from google.genai import types

client = genai.Client()

get_temp = types.FunctionDeclaration(
    name="get_current_temperature",
    description="Get temperature for a city.",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)

tools = [types.Tool(function_declarations=[get_temp])]

tool_config = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(
        mode="ANY",
    )
)

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="What's the weather in Tokyo?",
    config=types.GenerateContentConfig(tools=tools, tool_config=tool_config),
)

# If a functionCall is returned, execute it yourself, then send a follow-up turn
# with a functionResponse in contents.
```

### 8.2 Code execution tool
Enable with `tools=[{ codeExecution: {} }]` (JS) or `types.Tool(code_execution=...)` (Python).

---

## 9) Safety settings

Safety filters are configurable per request using `safetySettings`.
Thresholds include:
- `OFF`
- `BLOCK_NONE`
- `BLOCK_ONLY_HIGH`
- `BLOCK_MEDIUM_AND_ABOVE`
- `BLOCK_LOW_AND_ABOVE`

Docs note: for Gemini 2.5 and 3, default block threshold is **Off** if you don’t set it.

---

## 10) Context caching (long static context)

Caching lets you pay once to cache long inputs (system instruction + files/text) for repeated calls.

Key ideas:
- You create a cache with a TTL (defaults to 1 hour if not set).
- You reference it in calls via `cachedContent` / `cached_content`.

### Python (sketch)
```python
from google import genai
from google.genai import types

client = genai.Client()
model = "gemini-3-flash-preview"

cache = client.caches.create(
    model=model,
    config=types.CreateCachedContentConfig(
        display_name="my-cache",
        system_instruction="You are a formal proof assistant.",
        contents=["(very long context here)"],
        ttl="3600s",
    ),
)

resp = client.models.generate_content(
    model=model,
    contents="Now answer question Q using the cached context.",
    config=types.GenerateContentConfig(cached_content=cache.name),
)
```

---

## 11) OpenAI compatibility (optional)

You can call Gemini using OpenAI client libraries by setting:
- `base_url="https://generativelanguage.googleapis.com/v1beta/openai/"`
- `api_key="GEMINI_API_KEY"`
- `model="gemini-3-flash-preview"` (or `gemini-2.5-flash`)

Use this only if it reduces integration work; for full feature coverage, the native SDK/REST is usually clearer.

---

## 12) Practical defaults for formal proof + confidence/logprobs experiments

For “formal proof generation + confidence scoring” workflows:
- Start with `temperature=0.2~0.8` (Gemini 3 docs recommend default `1.0`; test before lowering too much).
- Enable `responseLogprobs=true` and `logprobs=5` (or 0 if you only need chosen token scores).
- Use `thinkingConfig.includeThoughts=false` in production runs (to reduce leakage/overhead), unless you explicitly study thought summaries.
- If you do tool loops on **Gemini 3**, prefer the official SDK or ensure you round-trip `thoughtSignature` fields in history.

