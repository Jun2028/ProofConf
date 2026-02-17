This repo lives in a remote HPC.

# Requirements:

- You should only request for CPU nodes for this task since GPUs are not required. Use multi-core or multi-thread for parallelizing and time saving whenever possible (e.g. parallelize Lean evaluations).

- Optimize for less compute use. That is, NEVER request too many cores more than needed, as well as don't set the wall time for the HPC task to too long. Always do a clear estimate of how much compute/cores are needed, and add some padding to that and use as the walltime/number of cores requested.

- Use `#PBS -P CFP01-SF-009` (project credit) by default. If not enough credit, use personal credit (by not including this flag in the .sh file).

- You may need to manually load the git module sometimes.

- Don't run everything on the login node, it can be wacky sometimes.

- See docs/VandaClusterUserGuide05Jun25.pdf for how to run commands/send tasks on the hpc, if you are unsure about anything.

- Any potentially huge data generated, like for the log props, **MUST** be stored in this folder:
`/scratch/USER/data/proofconf`. This is because the current directory that we are sitting on has limited storage, while the scratch folder has way more.