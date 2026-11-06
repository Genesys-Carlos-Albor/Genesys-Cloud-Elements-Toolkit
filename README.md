# Genesys Cloud Elements Toolkit

A desktop app and command-line tool that runs the Elements reports against Genesys Cloud orgs.
Each report saves a versioned Excel workbook (plus the raw JSON) and opens it when it finishes.
They are Python ports of the Elements PowerShell scripts.

## Install

**Windows:** download `Genesys Cloud Elements Toolkit.exe` from the
[Releases](https://github.com/Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit/releases) page and run it.
The instruction manual is attached to the same release.
No Python is needed. The exe is not code-signed, so the first time Windows SmartScreen may say
"Windows protected your PC": choose **More info**, then **Run anyway**.

**Mac (or Windows with Python):** install Python 3.11 or later from [python.org](https://www.python.org/downloads/), then:

```bash
pip install git+https://github.com/Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit.git
gctk-app
```

## Updates

The app checks GitHub for a newer release when it starts (and from **Check for updates**).
If there is one, it offers to download the new exe; close the app and run the new file in place of the old one.
Python installs update with:

```bash
pip install --upgrade git+https://github.com/Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit.git
```

`gctk version` shows the installed version and whether a newer one exists.

## First run

Add an org profile with **Add…** (name, region such as `usw2.pure.cloud`, OAuth client ID and secret),
or **Import from gc CLI** if you already use the `gc` command-line tool.
Use your own OAuth client: a Client Credentials grant with permission to read what the reports cover.
Secrets are stored in Windows Credential Manager or the macOS Keychain, never in files.

Reports save to `Element Reports` in your user folder by default; change this at the bottom of the app.

## Command line

```bash
gctk profiles list          # org profiles
gctk reports                # available reports
gctk run get-queues         # run a report (prompts for the org)
gctk run get-users --profile my-org --no-open
```

## Development

```bash
pip install -e ".[dev,build]"
pytest
powershell -File packaging\build_exe.ps1   # builds dist\Genesys Cloud Elements Toolkit.exe
```

Reports live in `src/gctoolkit/reports/`, one module per report, registered with `@register(...)`.

### Publishing a release

1. Raise `__version__` in `src/gctoolkit/__init__.py` (e.g. `0.2.0`) and commit.
2. Tag and push: `git tag v0.2.0` then `git push origin main v0.2.0`.

The **Release** GitHub Action runs the tests, builds the exe and publishes the release with the exe and
`docs/Genesys Cloud Elements Toolkit Instruction Manual.docx` attached. Update the manual in `docs/` before tagging:
releases are immutable, so files can't be added once one is published.
Installed apps see it the next time they start.
