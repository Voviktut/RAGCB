# Avito listing description parser

A small Python CLI for collecting Avito listing descriptions from a search/category URL and keeping only listings that mention **1–3 years of experience** (`1-3 года`, `1–3 года`, `1 до 3 лет`, etc.).

The default URL is the Avito Moscow business services accounting/finance category supplied in the task.

## Usage

```bash
python3 avito_experience_parser.py --output descriptions.xlsx
```

Useful options:

```bash
python3 avito_experience_parser.py \
  --url "https://www.avito.ru/moskva/predlozheniya_uslug/delovye_uslugi/buhgalteriya_finansy-ASgBAgICAkSYC7KfAZ4L9p8B" \
  --pages 3 \
  --delay 2 \
  --output descriptions.xlsx
```

The default Excel output has one row per listing. Column A contains the full description; columns B-D contain the title, source URL, and the matched experience fragment. Use a `.json` output path if you need raw JSON instead.

> Avito can block automated traffic. If requests are blocked, retry later, increase `--delay`, or provide browser-like headers via `--user-agent`.
