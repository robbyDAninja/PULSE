# OpenClaw Ecosystem Pulse

Automated weekly intelligence report tracking the OpenClaw ecosystem — core project, security advisories, spinoffs (IronClaw, ZeroClaw, NanoClaw, PicoClaw), and the broader AI agent framework landscape.

## How It Works

1. GitHub Actions runs every Monday at 9am ET
2. Fetches RSS feeds from 9 configured sources
3. Synthesizes articles through Claude API (Haiku 4.5)
4. Commits a structured markdown report to `reports/`

## Reports

Browse the [`reports/`](./reports) directory for all generated reports.

## Configuration

Edit `config.yml` to customize feeds, report format, and settings.

## Manual Run

Trigger manually from the Actions tab, or locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install -r requirements.txt
python generate_pulse.py
```

