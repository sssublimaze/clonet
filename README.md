# CLONET - Website Cloner

A pixel-perfect website cloning tool that downloads complete websites with all assets (HTML, CSS, JS, images, fonts) preserving the original structure.

## Features

- **Full page rendering** via Playwright (supports JavaScript-heavy SPAs)
- **Four cloning modes** for different use cases
- **Parallel asset downloads** with progress bar
- **Crawl depth control** for recursive site cloning
- **CSS processing** -- rewrites `url()` references and processes `@font-face` rules
- **Lazy-load support** -- scrolls pages to trigger lazy-loaded assets
- **Screenshot capture** for each cloned page
- **CLI flags and interactive menu** -- works both ways
- **Same-domain filtering** -- only downloads assets from the cloned domain

## Installation

```bash
pip install requests beautifulsoup4 playwright
playwright install chromium
```

Optional (for progress bars):

```bash
pip install tqdm
```

## Usage

### CLI mode

```bash
python clonet.py https://example.com -m 1 -o my_site
```

### Interactive mode

```bash
python clonet.py
```

Then follow the prompts to enter a URL and select a mode.

## Modes

| # | Mode | Description |
|---|------|-------------|
| 1 | **Landing Page** | Clones only the starting page. Fastest option. |
| 2 | **Full Site** | Recursive crawl through all same-domain links found on each page. |
| 3 | **Frontend Only** | Downloads HTML, CSS, and JS only. Skips images, videos, and other heavy media. |
| 4 | **Turbo** | Downloads raw HTML only. External asset URLs are preserved as-is; nothing is downloaded. |

## CLI Options

```
positional arguments:
  url                   URL of the site to clone

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   Output directory (default: domain name)
  -m, --mode {1,2,3,4}  Clone mode (see modes above)
  -d, --depth DEPTH     Maximum crawl depth (0 = unlimited)
  --no-screenshot       Disable page screenshots
  --no-banner           Hide the startup banner
```

### Examples

Clone a landing page with default settings:
```bash
python clonet.py https://example.com
```

Clone a full site with crawl depth of 3, save to a custom directory:
```bash
python clonet.py https://example.com -m 2 -d 3 -o my_backup
```

Quick HTML-only grab (Turbo mode):
```bash
python clonet.py https://example.com -m 4
```

Frontend code only (no images or video):
```bash
python clonet.py https://example.com -m 3 --no-screenshot
```

## How It Works

1. **Render** -- The URL is opened in a headless Chromium browser via Playwright, ensuring all JavaScript is executed and the DOM is fully built.
2. **Scroll** -- For full-site and landing-page modes, the page is automatically scrolled to trigger lazy-loaded images and content.
3. **Collect** -- HTML is parsed with BeautifulSoup to find all asset URLs (images, scripts, stylesheets, fonts, videos, iframes).
4. **Download** -- Assets from the same domain are downloaded in parallel using a thread pool.
5. **Rewrite** -- HTML is rewritten with local paths pointing to the downloaded assets. CSS files are also processed to fix `url()` references and `@font-face` `src` URLs.
6. **Crawl** -- In Full Site mode, all same-domain links are collected and queued for recursive cloning up to the specified depth.
7. **Save** -- Each page is saved as HTML with its directory structure mirroring the original URL path. A full-page screenshot is taken as a preview.

## Output Structure

```
output_dir/
  index.html
  css/
    style.css
  js/
    app.js
  images/
    logo.png
  fonts/
    custom.woff2
  about/
    index.html
  about/
    index_preview.png
```

Screenshots are saved alongside their HTML files with a `_preview.png` suffix.

## Dependencies

- Python 3.7+
- [playwright](https://github.com/microsoft/playwright-python)
- [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/)
- [requests](https://requests.readthedocs.io/)
- [tqdm](https://tqdm.github.io/) (optional)

## License

MIT
