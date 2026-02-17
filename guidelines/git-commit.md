gitignore the `.secret` folder, env files, HPC job log files and any run/test data generated.

## Git Push Policy

**NEVER auto-push commits to remote repositories.** Always let the user decide when to push changes.

- Only create local commits when requested
- Never run `git push` unless explicitly asked by the user
- After successful commits, inform the user they can push when ready
- Respect the user's workflow and timing for sharing changes