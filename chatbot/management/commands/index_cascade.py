"""
chatbot/management/commands/index_cascade.py
SITEMAP + FOLDER TRAVERSAL VERSION
"""

import re
import time
import httpx
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from chatbot.models import CMSPage
from chatbot.watsonx import watsonx_embed_batch, keyword_embed


SKIP_PATHS = {
    "-archived", "appfeed", "errors/", "_menu-panel",
    "index-test", "index-dev", "slate-branding", "logout",
    "search-results", "thankyou", "---index", "_archived",
    "_files", "_modules", "_internal", "_data", "_blocks",
    "_INTERNAL", "map/", "maps/img",
}


class Command(BaseCommand):
    help = "Crawl Cascade CMS and index new/changed pages into pgvector"

    def add_arguments(self, parser):
        parser.add_argument("--site",  type=str,            help="Filter by site name")
        parser.add_argument("--full",  action="store_true", help="Force re-index all pages")
        parser.add_argument("--clear", action="store_true", help="Wipe DB then re-index")

    def handle(self, *args, **options):
        if options["clear"]:
            count = CMSPage.objects.all().delete()[0]
            self.stdout.write(f"Cleared {count} existing pages from DB")

        force_full  = options.get("full", False)
        site_filter = options.get("site", "")

        sites = self._get_sites(site_filter)
        self.stdout.write(f"Found {len(sites)} site(s) to crawl")

        total_indexed   = 0
        total_skipped   = 0
        total_deleted   = 0
        all_cascade_ids = set()

        for site_name, site_id in sites:
            self.stdout.write(f"\n── Crawling: {site_name} ──")
            pages = self._crawl_site(site_name, site_id)
            self.stdout.write(f"   Found {len(pages)} pages")

            if not pages:
                continue

            for p in pages:
                all_cascade_ids.add(p["cascade_id"])

            indexed, skipped = self._smart_embed_and_store(pages, force_full)
            total_indexed += indexed
            total_skipped += skipped
            self.stdout.write(f"   Indexed: {indexed} | Skipped: {skipped}")

        if all_cascade_ids:
            deleted_qs    = CMSPage.objects.exclude(cascade_id__in=all_cascade_ids)
            total_deleted = deleted_qs.count()
            if total_deleted:
                self.stdout.write(f"\nRemoving {total_deleted} deleted pages...")
                deleted_qs.delete()

        self.stdout.write(
            f"\nDone!\n"
            f"  Indexed (new/changed):      {total_indexed}\n"
            f"  Skipped (unchanged):        {total_skipped}\n"
            f"  Deleted (removed from CMS): {total_deleted}"
        )

    def _auth(self) -> dict:
        return {"apiKey": settings.CASCADE_API_USER}

    def _should_skip(self, path: str) -> bool:
        for skip in SKIP_PATHS:
            if skip in path:
                return True
        return False

    def _get_sites(self, site_filter: str = "") -> list[tuple[str, str]]:
        url = f"{settings.CASCADE_BASE_URL}/api/v1/listSites"
        try:
            r      = httpx.get(url, params=self._auth(), timeout=15)
            data   = r.json()
            assets = data.get("sites", [])

            if not isinstance(assets, list):
                assets = []

            results = []
            for a in assets:
                site_id   = a.get("id", "")
                path_obj  = a.get("path", {})
                site_name = path_obj.get("path", "") if isinstance(path_obj, dict) else ""

                if site_name.startswith("_"):
                    continue
                if site_filter and site_filter.lower() not in site_name.lower():
                    continue
                if not site_filter:
                    if any(x in site_name.lower() for x in ["test", "dev", "staging"]):
                        continue

                if site_id and site_name:
                    results.append((site_name, site_id))
                    self.stdout.write(f"   Site: {site_name} → {site_id}")

            return results if results else [(settings.CASCADE_SITE, settings.CASCADE_SITE)]

        except Exception as e:
            self.stderr.write(f"Could not list sites: {e}")
            return [(settings.CASCADE_SITE, settings.CASCADE_SITE)]

    # ── Crawl site ─────────────────────────────────────────────

    def _crawl_site(self, site_name: str, site_id: str) -> list[dict]:
        all_pages = []
        seen_ids  = set()

        # Step 1 — get folders from sitemap (no hardcoding)
        self.stdout.write("   Fetching folders from sitemap...")
        folders = self._get_folders_from_sitemap(site_name)
        self.stdout.write(f"   Sitemap folders: {sorted(folders)}")

        # Step 2 — also get folders from CMS search (catches any not in sitemap)
        self.stdout.write("   Fetching folders from CMS search...")
        search_folders = self._get_folders_from_search(site_id)
        self.stdout.write(f"   Search folders: {sorted(search_folders)}")

        # Step 3 — combine both sources
        all_folders = sorted(set(folders) | set(search_folders))
        self.stdout.write(f"   Total unique folders to crawl: {len(all_folders)}")
        self.stdout.write(f"   Folders: {all_folders}")

        # Step 4 — recursively crawl each folder
        for folder in all_folders:
            self.stdout.write(f"\n   → crawling: {folder}")
            self._crawl_folder(site_name, folder, all_pages, seen_ids)
            self.stdout.write(f"   total so far: {len(all_pages)}")

        return all_pages

    # ── Get folders from sitemap ───────────────────────────────

    def _get_folders_from_sitemap(self, site_name: str) -> set[str]:
        """
        Fetch live sitemap and extract all top-level folder names.
        This is the most reliable source — covers everything published.
        """
        # build sitemap URL from site name
        # site_name = "ontariotechu.ca" → "https://ontariotechu.ca/sitemap.xml"
        sitemap_url = f"https://{site_name}/sitemap.xml"

        try:
            r = httpx.get(sitemap_url, timeout=15, follow_redirects=True)
            if r.status_code != 200:
                self.stderr.write(f"   Sitemap returned {r.status_code}")
                return set()

            content = r.text
            # extract all URLs from sitemap
            urls = re.findall(r'<loc>(https?://[^<]+)</loc>', content)
            self.stdout.write(f"   Sitemap has {len(urls)} URLs")

            folders = set()
            base = f"https://{site_name}/"

            for url in urls:
                if not url.startswith(base):
                    continue

                # extract path after domain
                path = url.replace(base, "").strip("/")

                # remove .php extension
                path = re.sub(r'\.php$', '', path)

                if not path:
                    continue

                # get top-level folder (first segment)
                folder = path.split("/")[0]

                if not folder:
                    continue
                if folder.startswith("_"):
                    continue
                if folder.startswith("-"):
                    continue
                if self._should_skip(folder):
                    continue

                folders.add(folder)

            return folders

        except Exception as e:
            self.stderr.write(f"   Sitemap error: {e}")
            return set()

    # ── Get folders from CMS search ───────────────────────────

    def _get_folders_from_search(self, site_id: str) -> set[str]:
        """
        Search CMS for top-level folders using broad terms.
        Catches folders not published to live site.
        """
        search_terms = [
            "a", "e", "i", "o", "u",
            "s", "c", "p", "r", "m",
            "f", "g", "h", "t", "w",
        ]

        folders = set()

        for term in search_terms:
            url  = f"{settings.CASCADE_BASE_URL}/api/v1/search"
            body = {
                "searchInformation": {
                    "searchTerms":  term,
                    "searchFields": ["name"],
                    "searchTypes":  ["folder"],
                    "siteId":       site_id,
                }
            }

            try:
                r       = httpx.post(url, params=self._auth(), json=body, timeout=30)
                data    = r.json()
                matches = data.get("matches", [])

                if isinstance(matches, dict):
                    matches = matches.get("match", [])
                if isinstance(matches, dict):
                    matches = [matches]
                if not isinstance(matches, list):
                    continue

                for m in matches:
                    path_obj    = m.get("path", {})
                    folder_path = path_obj.get("path", "")

                    if not folder_path:
                        continue
                    if "/" in folder_path:       # top level only
                        continue
                    if folder_path.startswith("_"):
                        continue
                    if folder_path.startswith("-"):
                        continue
                    if self._should_skip(folder_path):
                        continue

                    folders.add(folder_path)

            except Exception:
                pass

            time.sleep(0.05)

        return folders

    # ── Recursive folder crawl ─────────────────────────────────

    def _crawl_folder(
        self,
        site: str,
        folder_path: str,
        all_pages: list,
        seen_ids: set,
        depth: int = 0,
    ):
        """Recursively read a folder and all its children."""

        if depth > 15:   # safety limit
            return

        path = folder_path.strip("/")
        url  = f"{settings.CASCADE_BASE_URL}/api/v1/read/folder/{site}/{path}"

        try:
            r    = httpx.get(url, params=self._auth(), timeout=15)
            data = r.json()

            if not data.get("success"):
                return

            folder   = data["asset"]["folder"]
            children = folder.get("children", [])

            if isinstance(children, dict):
                children = [children]
            if not isinstance(children, list):
                return

            for child in children:
                child_type = child.get("type", "")
                path_obj   = child.get("path", {})
                child_path = path_obj.get("path", "") if isinstance(path_obj, dict) else ""
                child_site = path_obj.get("siteName", site)

                if not child_path:
                    continue

                if self._should_skip(child_path):
                    continue

                if child_type == "page":
                    page_id = child.get("id", child_path)
                    if page_id in seen_ids:
                        continue
                    seen_ids.add(page_id)

                    page = self._read_page(child_site, child_path)
                    if page:
                        all_pages.append(page)
                        indent = "  " * depth
                        self.stdout.write(f"     {indent}✓ {child_path}")

                    time.sleep(0.05)

                elif child_type == "folder":
                    indent = "  " * depth
                    self.stdout.write(f"     {indent}→ {child_path}")
                    self._crawl_folder(
                        child_site, child_path,
                        all_pages, seen_ids,
                        depth + 1
                    )

        except Exception as e:
            self.stderr.write(f"   Folder error [{folder_path}]: {e}")

    # ── Read single page ───────────────────────────────────────

    def _read_page(self, site: str, path: str) -> dict | None:
        path = path.lstrip("/")
        url  = f"{settings.CASCADE_BASE_URL}/api/v1/read/page/{site}/{path}"
        try:
            r = httpx.get(url, params=self._auth(), timeout=8)
            r.raise_for_status()
            data = r.json()

            if not data.get("success"):
                return None

            page = data["asset"]["page"]
            meta = page.get("metadata", {})

            raw_html = page.get("xhtml", "") or ""

            if not raw_html.strip():
                raw_html = self._extract_structured_text(
                    page.get("structuredData", {})
                )

            text = re.sub(r"<[^>]+>", " ", raw_html)
            text = re.sub(r"\s+",      " ", text).strip()

            if not text:
                text = (
                    meta.get("metaDescription", "")
                    or meta.get("summary", "")
                    or meta.get("teaser", "")
                    or ""
                ).strip()

            if not text:
                return None

            clean_path = path if path.startswith("/") else f"/{path}"
            public_url = f"https://ontariotechu.ca{clean_path}"

            return {
                "cascade_id":    page.get("id", ""),
                "path":          path,
                "site":          site,
                "title":         (
                    meta.get("title")
                    or meta.get("displayName")
                    or page.get("name", path)
                ),
                "content":       text[:2000],
                "url":           public_url,
                "last_modified": page.get("lastModifiedDate"),
            }

        except httpx.TimeoutException:
            self.stderr.write(f"   Timeout [{path}]")
            return None
        except Exception:
            return None

    # ── Extract structured text ────────────────────────────────

    def _extract_structured_text(self, structured_data: dict) -> str:
        texts = []

        SKIP_VALUES = {
            "No", "Yes", "Internal", "External",
            "Standard content", "CMS block", "Standard columns",
            "Embed code", "Feature module", "Same window",
            "Alphabetical", "Left", "Right", "Center", "Accent",
            "Banner block", "Medium blue", "Dark blue", "Light blue",
            "Image/video only", "Expanded page", "Standard",
            "Expanded", "Default", "large", "standard",
            "Learn more", "Placeholder",
        }

        def walk(node):
            if isinstance(node, dict):
                val = node.get("text", "")
                if (
                    val
                    and not val.startswith("::")
                    and val not in SKIP_VALUES
                    and len(val) > 20
                    and not val.strip().startswith("<style")
                    and not val.strip().startswith("<script")
                ):
                    texts.append(val.strip())
                for child in node.get("structuredDataNodes", []):
                    walk(child)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(structured_data)
        return " ".join(texts)

    # ── Smart embed and store ──────────────────────────────────

    def _smart_embed_and_store(
        self, pages: list[dict], force_full: bool = False
    ) -> tuple[int, int]:
        from django.utils.dateparse import parse_datetime

        indexed  = 0
        skipped  = 0
        to_index = []

        for page in pages:
            if force_full:
                to_index.append(page)
                continue

            existing = CMSPage.objects.filter(
                cascade_id=page["cascade_id"]
            ).first()

            if existing is None:
                self.stdout.write(f"   NEW:     {page['title'][:60]}")
                to_index.append(page)
            else:
                cms_modified = parse_datetime(page["last_modified"]) if page["last_modified"] else None

                if (
                    existing.last_modified is None
                    or cms_modified is None
                    or existing.last_modified != cms_modified
                ):
                    self.stdout.write(f"   CHANGED: {page['title'][:60]}")
                    to_index.append(page)
                else:
                    skipped += 1

        if not to_index:
            return 0, skipped

        self.stdout.write(f"\n   Embedding {len(to_index)} pages...")

        BATCH = getattr(settings, "CASCADE_CRAWL_BATCH", 50)

        for i in range(0, len(to_index), BATCH):
            batch         = to_index[i : i + BATCH]
            texts         = [f"{p['title']} {p['content']}" for p in batch]
            total_batches = (len(to_index) + BATCH - 1) // BATCH

            self.stdout.write(f"   Batch {i // BATCH + 1}/{total_batches} — {len(batch)} pages")

            try:
                vectors = watsonx_embed_batch(texts)
                self.stdout.write("   watsonx: OK")
            except Exception as e:
                self.stderr.write(f"   watsonx error: {e} — keyword fallback")
                vectors = [keyword_embed(t) for t in texts]

            for page, vec in zip(batch, vectors):
                try:
                    cms_modified = parse_datetime(page["last_modified"]) if page["last_modified"] else None

                    CMSPage.objects.update_or_create(
                        cascade_id=page["cascade_id"],
                        defaults={
                            "path":          page["path"],
                            "site":          page["site"],
                            "title":         page["title"],
                            "content":       page["content"],
                            "url":           page["url"],
                            "embedding":     vec,
                            "last_modified": cms_modified,
                            "indexed_at":    timezone.now(),
                        },
                    )
                    indexed += 1
                except Exception as e:
                    self.stderr.write(f"   Store error [{page['path']}]: {e}")

            time.sleep(0.3)

        return indexed, skipped