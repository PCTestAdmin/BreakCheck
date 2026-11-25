# Project website

The static site is in this directory (index.html, site.css and brand.svg). No JavaScript, tracking, external font requests or build dependencies are required. Download links point to the latest published release, which may lag behind main.

Preview from the repository root with python3 -m http.server 8000 --directory docs, then open http://127.0.0.1:8000.

To publish on GitHub Pages, a repository administrator must open Settings > Pages, choose Deploy from a branch, select main and /docs, and save. The site is not automatically published by the package workflow. The expected project URL after successful deployment is https://pctestadmin.github.io/BreakCheck/. GitHub Pages availability depends on repository settings.
