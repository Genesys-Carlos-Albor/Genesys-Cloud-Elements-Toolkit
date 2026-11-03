# Genesys Cloud Elements Toolkit

A desktop app and command-line tool that runs the Elements reports against Genesys Cloud orgs.
Each report saves a versioned Excel workbook (plus the raw JSON) and opens it when it finishes.
They are Python ports of the Elements PowerShell scripts.

## Install

**Windows:** download `Genesys Cloud Elements Toolkit.exe` from the
[Releases](https://github.com/Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit/releases) page and run it.
No Python is needed. The exe is not code-signed, so the first time Windows SmartScreen may say
"Windows protected your PC": choose **More info**, then **Run anyway**.

**Mac (or Windows with Python):** install Python 3.11 or later from [python.org](https://www.python.org/downloads/), then:

```bash
pip install git+https://github.com/Genesys-Carlos-Albor/Genesys-Cloud-Elements-Toolkit.git
gctk-app
```

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
