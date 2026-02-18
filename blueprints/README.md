# Blueprints

> Master playbook for all chrbailey repositories. Open Claude Code in any
> repo and say: "Look at ~/lex-intel/blueprints/ and apply the relevant
> patterns to this project."

## What's Here

| Blueprint | Purpose |
|-----------|---------|
| [repo-standards.md](repo-standards.md) | Naming, structure, README format, required files |
| [llms-txt.md](llms-txt.md) | How to create llms.txt for agent discovery |
| [github-pages.md](github-pages.md) | Agent-optimized GitHub Pages setup |
| [claude-md.md](claude-md.md) | CLAUDE.md template for Claude Code |
| [agent-publishing.md](agent-publishing.md) | Automated content publishing via GitHub Actions |
| [hub-site.md](hub-site.md) | Design for chrbailey.github.io master site |

## How to Use

### From Claude Code CLI (on your Mac Mini)

```
cd ~/some-other-repo
claude

> "Read ~/lex-intel/blueprints/repo-standards.md and apply those
>  conventions to this repo. Also create an llms.txt using the
>  template from ~/lex-intel/blueprints/llms-txt.md"
```

### From Claude Code Web (on iPhone)

Reference the GitHub URLs directly:

```
> "Read https://github.com/chrbailey/lex-intel/blob/main/blueprints/repo-standards.md
>  and apply those patterns to this repo"
```

## Application Order

When standardizing a repo from scratch:

1. **repo-standards.md** — restructure README, add required files
2. **claude-md.md** — create CLAUDE.md
3. **llms-txt.md** — create llms.txt
4. **github-pages.md** — set up Pages (if public repo)
5. **agent-publishing.md** — add auto-publish pipeline (if produces output)
6. **hub-site.md** — reference only; used for the master site
