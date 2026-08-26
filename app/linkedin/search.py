import urllib.parse
import re
import time
from typing import List, Dict, Any, Optional
try:
    from playwright.sync_api import BrowserContext, Page
except ImportError:
    BrowserContext = Any
    Page = Any
from app.utils.logger import setup_logger

logger = setup_logger("linkedin.search")


class LinkedInSearcher:
    def __init__(self, context: BrowserContext):
        self.context = context

    def search_posts(self, query: str, max_results: int = 25) -> List[Dict[str, Any]]:
        """Searches LinkedIn posts for the query with past-24h filter and collects raw post data."""
        page: Page = self.context.new_page()
        encoded_query = urllib.parse.quote(query)
        # LinkedIn content/posts search sorted by date posted (past 24h)
        search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&sortBy=%22date_posted%22"

        logger.info(f"Navigating to LinkedIn search: {search_url}")
        results: List[Dict[str, Any]] = []

        try:
            page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)

            # Scroll down smoothly to trigger dynamic lazy loading of post cards
            scroll_count = 0
            while len(results) < max_results and scroll_count < 6:
                # Extract post elements supporting both standard and modern SDUI listitems
                post_elements = page.query_selector_all(
                    "div[role='listitem'], div.feed-shared-update-v2, div[data-urn*='activity'], div[data-component-type='LazyColumn'] > div > div, div.search-results-container div.artdeco-card"
                )

                logger.info(f"Discovered {len(post_elements)} post containers on page (scroll pass {scroll_count + 1})")

                for elem in post_elements:
                    try:
                        try:
                            inner_html = elem.inner_html() if hasattr(elem, "inner_html") else ""
                            if not isinstance(inner_html, str):
                                inner_html = str(inner_html)
                        except Exception:
                            inner_html = ""

                        try:
                            full_elem_text = elem.inner_text().strip() if hasattr(elem, "inner_text") else ""
                            if not isinstance(full_elem_text, str):
                                full_elem_text = str(full_elem_text)
                        except Exception:
                            full_elem_text = ""

                        # Extract post text / description
                        text_elem = elem.query_selector(
                            ".feed-shared-update-v2__description, .feed-shared-text, .update-components-text, .break-words, div[componentkey*='update'], div[data-testid*='post-text']"
                        )
                        raw_text = text_elem.inner_text().strip() if text_elem and hasattr(text_elem, "inner_text") else full_elem_text
                        if not raw_text or len(raw_text) < 15:
                            continue

                        # Extract author / recruiter name
                        author_elem = elem.query_selector(
                            ".update-components-actor__name, .feed-shared-actor__name, a[href*='/in/'], span.visually-hidden"
                        )
                        author_name = author_elem.inner_text().strip() if author_elem else "Recruiter"

                        # Extract author title / company
                        actor_desc_elem = elem.query_selector(
                            ".update-components-actor__description, .feed-shared-actor__description"
                        )
                        author_headline = actor_desc_elem.inner_text().strip() if actor_desc_elem else ""

                        # Extract post timestamp
                        time_elem = elem.query_selector(
                            ".update-components-actor__sub-description, .feed-shared-actor__sub-description, time"
                        )
                        posted_at = time_elem.inner_text().strip() if time_elem else ""
                        if not posted_at:
                            # Fallback regex for time strings in card text
                            m_time = re.search(r"\b(\d+[mhdw]|just now|\d+\s*hours?|\d+\s*days?)\b", full_elem_text, re.IGNORECASE)
                            posted_at = m_time.group(1) if m_time else "1h"

                        # Extract authentic post URL or URN
                        post_url = ""
                        # 1. Direct href match for update/posts
                        url_elem = elem.query_selector("a[href*='/feed/update/'], a[href*='/posts/'], a[href*='activity-']")
                        if url_elem:
                            href = url_elem.get_attribute("href")
                            if href:
                                post_url = href.split("?")[0]
                                if not post_url.startswith("http"):
                                    post_url = f"https://www.linkedin.com{post_url}"

                        # 2. Check for highlightedUpdateUrn in links
                        if not post_url:
                            group_elem = elem.query_selector("a[href*='highlightedUpdateUrn=']")
                            if group_elem:
                                g_href = group_elem.get_attribute("href") or ""
                                m_urn = re.search(r"highlightedUpdateUrn=(urn%3A[^&]+|urn:[^&]+)", g_href)
                                if m_urn:
                                    raw_urn = urllib.parse.unquote(m_urn.group(1))
                                    post_url = f"https://www.linkedin.com/feed/update/{raw_urn}/"

                        # 3. Check data-urn or data-id
                        if not post_url:
                            urn = elem.get_attribute("data-urn") or elem.get_attribute("data-id") or ""
                            if not urn:
                                inner_urn_elem = elem.query_selector("[data-urn], [data-id]")
                                if inner_urn_elem:
                                    urn = inner_urn_elem.get_attribute("data-urn") or inner_urn_elem.get_attribute("data-id") or ""
                            if urn and ("activity:" in urn or "ugcPost:" in urn or "share:" in urn):
                                post_url = f"https://www.linkedin.com/feed/update/{urn}/"

                        # 4. Check regex in HTML
                        if not post_url:
                            m_raw = re.search(r"urn:li:activity:(\d+)", inner_html)
                            if m_raw:
                                post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{m_raw.group(1)}/"

                        if not post_url:
                            logger.debug("Skipping container: could not resolve authentic LinkedIn post URL.")
                            continue

                        item = {
                            "post_url": post_url,
                            "author_name": author_name,
                            "author_headline": author_headline,
                            "posted_at": posted_at,
                            "raw_text": raw_text,
                        }

                        # Deduplicate in current batch
                        if not any(r["post_url"] == post_url for r in results):
                            results.append(item)
                            if len(results) >= max_results:
                                break
                    except Exception as item_err:
                        logger.debug(f"Skipping container due to parse error: {item_err}")

                # Scroll down smoothly
                page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                time.sleep(2.5)
                scroll_count += 1

        except Exception as e:
            logger.error(f"Error during LinkedIn search: {e}")
            raise e
        finally:
            page.close()

        logger.info(f"Total raw posts discovered: {len(results)}")
        return results

        logger.info(f"Total raw posts discovered: {len(results)}")
        return results
