Set up this repo referring to the first conversation in the `conversions` folder.

- You do not have to follow the repo's file outline in the conversations exactly. That is just a reference.

- set up the required python env using uv. set up the lean env according to the miniF2F dataset's deps.

- The paper for the Confidence metrics is at docs/2508.15260v1.pdf.

- Log the setup tests (that the env/each component works) in `set-up-logs` folder.

- Fill-up/improve each .md file for clarity, if needed.

- Run an initial test with the appropriate conf metrics on the appropriate questions (small but non-trivial number of questions and LLM calls.). 

- Try with DeepSeek only. 

- Write the README after everything is done (introduce purpose, illustrate clearly how the confidence of a LLM-generated Lean proof is computed, structure of the repo, how to run, first run results like in any README). 