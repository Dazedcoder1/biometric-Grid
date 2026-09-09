# Screenshots for SETUP.md

`SETUP.md` references four screenshots. Drop the PNGs here with these exact
filenames and they will appear in the guide on GitHub.

| Filename | What to capture |
|----------|-----------------|
| `01-github-token.png` | The fine-grained token page at `github.com/settings/personal-access-tokens/new`, scrolled to Repository permissions with **Issues: Read and write** selected |
| `02-connect-github.png` | Tenant Admin → **Tasks** → the **Connect GitHub** panel open, repo and token fields visible |
| `03-username-mapping.png` | Tenant Admin → **GitHub Repos** → the *GitHub usernames* table at the bottom |
| `04-webhook.png` | The repo's **Settings → Webhooks → Add webhook** form, filled in |

Then uncomment the image lines in `SETUP.md` — each placeholder looks like:

```markdown
> 📷 *Screenshot to add: `docs/images/01-github-token.png` — ...*
```

Replace with:

```markdown
![Creating a fine-grained token with Issues write access](docs/images/01-github-token.png)
```

## Before you commit

**Blur or crop any real token, webhook secret or API key.** A screenshot of a
token is as good as the token itself. The safest approach is to capture the
screens *before* pasting a real value, or to use an obviously fake placeholder
like `github_pat_EXAMPLE_NOT_REAL`.
