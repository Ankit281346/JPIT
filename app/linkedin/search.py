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

    def search_posts(self, query: Any, max_results: int = 80) -> List[Dict[str, Any]]:
        """Searches LinkedIn posts across primary query and related phrase variations until target post volume is met."""
        if isinstance(query, str):
            from app.resume.analyzer import ResumeAnalyzer
            analyzer = ResumeAnalyzer()
            queries = [query]
            variations = analyzer.generate_query_variations(query)
            for v in variations:
                if v not in queries:
                    queries.append(v)
        elif isinstance(query, list):
            queries = query
        else:
            queries = [str(query)]

        results: List[Dict[str, Any]] = []
        page: Page = self.context.new_page()

        try:
            for q_idx, current_q in enumerate(queries):
                if len(results) >= max_results:
                    break

                encoded_query = urllib.parse.quote(current_q)
                search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&sortBy=%22date_posted%22"
                logger.info(f"Searching phrase variation [{q_idx+1}/{len(queries)}]: '{current_q}' (Current total: {len(results)}/{max_results} posts)")

                try:
                    page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
                    time.sleep(3.5)

                    scroll_count = 0
                    max_scrolls = 20 if len(queries) > 1 else 35

                    while len(results) < max_results and scroll_count < max_scrolls:
                        # 1. Automatically click all "...see more" buttons so full post description (with recruiter email) is revealed
                        try:
                            page.evaluate("""
                            () => {
                                const seeMoreBtns = document.querySelectorAll(
                                    "button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*='see more' i], button.feed-shared-see-more, button[aria-label*='more' i]"
                                );
                                seeMoreBtns.forEach(b => { try { b.click(); } catch(e) {} });

                                // Also click 'Show more results' if LinkedIn stops auto-scrolling
                                const showMore = Array.from(document.querySelectorAll("button")).filter(
                                    b => b.innerText && (b.innerText.toLowerCase().includes("show more results") || b.innerText.toLowerCase().includes("see more results"))
                                );
                                showMore.forEach(b => { try { b.click(); } catch(e) {} });
                            }
                            """)
                        except Exception:
                            pass

                        time.sleep(0.8)

                        # Extract post elements supporting both standard and modern SDUI listitems
                        post_elements = page.query_selector_all(
                            "div[role='listitem'], div.feed-shared-update-v2, div[data-urn*='activity'], div[data-component-type='LazyColumn'] > div > div, div.search-results-container div.artdeco-card"
                        )

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
                                    m_time = re.search(r"\b(\d+[mhdw]|just now|\d+\s*hours?|\d+\s*days?)\b", full_elem_text, re.IGNORECASE)
                                    posted_at = m_time.group(1) if m_time else "1h"

                                # Extract authentic post URL or URN
                                post_url = ""
                                url_elem = elem.query_selector("a[href*='/feed/update/'], a[href*='/posts/'], a[href*='activity-']")
                                if url_elem:
                                    href = url_elem.get_attribute("href")
                                    if href:
                                        post_url = href.split("?")[0]
                                        if not post_url.startswith("http"):
                                            post_url = f"https://www.linkedin.com{post_url}"

                                if not post_url:
                                    group_elem = elem.query_selector("a[href*='highlightedUpdateUrn=']")
                                    if group_elem:
                                        g_href = group_elem.get_attribute("href") or ""
                                        m_urn = re.search(r"highlightedUpdateUrn=(urn%3A[^&]+|urn:[^&]+)", g_href)
                                        if m_urn:
                                            raw_urn = urllib.parse.unquote(m_urn.group(1))
                                            post_url = f"https://www.linkedin.com/feed/update/{raw_urn}/"

                                if not post_url:
                                    urn = elem.get_attribute("data-urn") or elem.get_attribute("data-id") or ""
                                    if not urn:
                                        inner_urn_elem = elem.query_selector("[data-urn], [data-id]")
                                        if inner_urn_elem:
                                            urn = inner_urn_elem.get_attribute("data-urn") or inner_urn_elem.get_attribute("data-id") or ""
                                    if urn and ("activity:" in urn or "ugcPost:" in urn or "share:" in urn):
                                        post_url = f"https://www.linkedin.com/feed/update/{urn}/"

                                if not post_url:
                                    m_raw = re.search(r"urn:li:activity:(\d+)", inner_html)
                                    if m_raw:
                                        post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{m_raw.group(1)}/"

                                if not post_url:
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

                        # Scroll down to load next wave of posts
                        page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                        time.sleep(1.8)
                        scroll_count += 1

                except Exception as sub_err:
                    logger.warning(f"Error during query variation '{current_q}': {sub_err}")

        except Exception as e:
            logger.error(f"Error during LinkedIn multi-phrase search: {e}")
            raise e
        finally:
            page.close()

        logger.info(f"Total raw posts discovered across similar phrase queries: {len(results)}")
        return results

        logger.info(f"Total raw posts discovered: {len(results)}")
        return results
