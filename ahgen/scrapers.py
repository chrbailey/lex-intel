"""
China Source Scrapers for Ahgen Media Manager.

Tier 1 sources for ERP/tech intelligence from Chinese-language sites.
Each scraper returns a list of article dicts with standardized format.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict
import httpx
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET


# Common headers to avoid blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Timeout for all requests (seconds)
TIMEOUT = 30


def _now_iso() -> str:
    """Return current time in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(element) -> str:
    """Extract text from BeautifulSoup element, return empty string if None."""
    return element.get_text(strip=True) if element else ""


def fetch_36kr() -> List[Dict]:
    """
    Fetch articles from 36Kr tech news.
    Uses RSS feed at 36kr.com/feed for reliability.
    """
    articles = []
    try:
        response = httpx.get(
            "https://36kr.com/feed",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        # Parse RSS XML
        root = ET.fromstring(response.text)

        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            description = item.find("description")
            pub_date = item.find("pubDate")

            articles.append({
                "source": "36kr",
                "title": title.text if title is not None else "",
                "url": link.text if link is not None else "",
                "content": description.text if description is not None else "",
                "published": pub_date.text if pub_date is not None else _now_iso(),
            })

    except Exception as e:
        print(f"[36kr] Error fetching: {e}")

    return articles


def fetch_huxiu() -> List[Dict]:
    """
    Fetch articles from Huxiu (huxiu.com) tech news.
    Scrapes the homepage article list.
    """
    articles = []
    seen_urls = set()  # Dedupe by URL
    try:
        response = httpx.get(
            "https://www.huxiu.com/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find all article links directly
        for link_el in soup.select("a[href*='/article/']")[:50]:
            url = link_el.get("href", "")
            if not url or url in seen_urls:
                continue

            if not url.startswith("http"):
                url = "https://www.huxiu.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get title from link text or parent
            title = _safe_text(link_el)
            if not title or len(title) < 5:
                continue

            articles.append({
                "source": "huxiu",
                "title": title,
                "url": url,
                "content": "",
                "published": _now_iso(),
            })

            if len(articles) >= 20:
                break

    except Exception as e:
        print(f"[huxiu] Error fetching: {e}")

    return articles


def fetch_infoq_china() -> List[Dict]:
    """
    Fetch articles from InfoQ China (infoq.cn).
    Has RSS feed for tech articles.
    """
    articles = []
    try:
        # Try RSS first
        response = httpx.get(
            "https://www.infoq.cn/feed",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )

        if response.status_code == 200 and "xml" in response.headers.get("content-type", ""):
            root = ET.fromstring(response.text)
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                description = item.find("description")
                pub_date = item.find("pubDate")

                articles.append({
                    "source": "infoq_china",
                    "title": title.text if title is not None else "",
                    "url": link.text if link is not None else "",
                    "content": description.text if description is not None else "",
                    "published": pub_date.text if pub_date is not None else _now_iso(),
                })
        else:
            # Fallback to homepage scraping
            response = httpx.get(
                "https://www.infoq.cn/",
                headers=HEADERS,
                timeout=TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            for article in soup.select("div.article-item, article, a[href*='/article/']")[:20]:
                title_el = article.select_one("h2, h3, span[class*='title']")
                link_el = article if article.name == "a" else article.select_one("a[href*='/article/']")
                summary_el = article.select_one("p, span[class*='summary']")

                if title_el and link_el:
                    url = link_el.get("href", "")
                    if url and not url.startswith("http"):
                        url = "https://www.infoq.cn" + url

                    articles.append({
                        "source": "infoq_china",
                        "title": _safe_text(title_el),
                        "url": url,
                        "content": _safe_text(summary_el),
                        "published": _now_iso(),
                    })

    except Exception as e:
        print(f"[infoq_china] Error fetching: {e}")

    return articles


def fetch_csdn() -> List[Dict]:
    """
    Fetch articles from CSDN (csdn.net) tech community.
    Scrapes the hot/recommended articles page.
    """
    articles = []
    try:
        response = httpx.get(
            "https://blog.csdn.net/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # CSDN has article list with various container classes
        for article in soup.select("div.blog-list-item, div[class*='article'], article")[:20]:
            title_el = article.select_one("h2, h3, a[class*='title'], span[class*='title']")
            link_el = article.select_one("a[href*='blog.csdn.net'], a[href*='/article/']")
            summary_el = article.select_one("p, div[class*='content'], div[class*='desc']")

            if title_el and link_el:
                url = link_el.get("href", "")
                if url and not url.startswith("http"):
                    url = "https://blog.csdn.net" + url

                articles.append({
                    "source": "csdn",
                    "title": _safe_text(title_el),
                    "url": url,
                    "content": _safe_text(summary_el),
                    "published": _now_iso(),
                })

    except Exception as e:
        print(f"[csdn] Error fetching: {e}")

    return articles


def fetch_sap_china() -> List[Dict]:
    """
    Fetch news from SAP News Center.
    Covers global SAP news including ERP announcements.
    """
    articles = []
    seen_urls = set()
    try:
        response = httpx.get(
            "https://news.sap.com/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # SAP news uses article elements with links
        for link_el in soup.select("a[href*='news.sap.com/20']")[:30]:
            url = link_el.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Get heading inside link
            heading = link_el.select_one("h2, h3, h4")
            title = _safe_text(heading) if heading else _safe_text(link_el)

            if title and len(title) > 10:
                articles.append({
                    "source": "sap_news",
                    "title": title[:200],
                    "url": url,
                    "content": "",
                    "published": _now_iso(),
                })

            if len(articles) >= 15:
                break

    except Exception as e:
        print(f"[sap_news] Error fetching: {e}")

    return articles


def fetch_kingdee() -> List[Dict]:
    """
    Fetch news from Kingdee (kingdee.com).
    Scrapes global news and blog sections.
    """
    articles = []
    seen_urls = set()
    try:
        # Kingdee global news
        response = httpx.get(
            "https://www.kingdee.com/global/news/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find all blog/news links
        for link_el in soup.select("a[href*='/blog/'], a[href*='/news/']")[:50]:
            url = link_el.get("href", "")
            if not url or url in seen_urls or url.endswith("/news/") or url.endswith("/blog/"):
                continue

            if not url.startswith("http"):
                url = "https://www.kingdee.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get title from heading inside or link text
            title_el = link_el.select_one("h2, h3, h4")
            title = _safe_text(title_el) if title_el else _safe_text(link_el)

            if title and len(title) > 5:
                articles.append({
                    "source": "kingdee",
                    "title": title[:200],  # Truncate long titles
                    "url": url,
                    "content": "",
                    "published": _now_iso(),
                })

            if len(articles) >= 20:
                break

    except Exception as e:
        print(f"[kingdee] Error fetching: {e}")

    return articles


def fetch_yonyou() -> List[Dict]:
    """
    Fetch news from Yonyou (yonyou.com).
    Tries multiple endpoints since main site blocks scrapers.
    """
    articles = []
    seen_urls = set()

    # Try different Yonyou URLs
    urls_to_try = [
        "https://www.yonyou.com/",
        "https://www.yonyoucloud.com/",
    ]

    for base_url in urls_to_try:
        try:
            response = httpx.get(
                base_url,
                headers={
                    **HEADERS,
                    "Referer": "https://www.google.com/",
                },
                timeout=TIMEOUT,
                follow_redirects=True,
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            # Find news/article links
            for link_el in soup.select("a[href*='news'], a[href*='article'], a[href*='blog']")[:30]:
                url = link_el.get("href", "")
                if not url or url in seen_urls:
                    continue

                if not url.startswith("http"):
                    url = base_url.rstrip("/") + url

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = _safe_text(link_el)
                if title and len(title) > 5:
                    articles.append({
                        "source": "yonyou",
                        "title": title[:200],
                        "url": url,
                        "content": "",
                        "published": _now_iso(),
                    })

                if len(articles) >= 15:
                    break

            if articles:
                break  # Got results, stop trying

        except Exception as e:
            print(f"[yonyou] Error with {base_url}: {e}")
            continue

    return articles


def fetch_leiphone() -> List[Dict]:
    """
    Fetch articles from LeiPhone (leiphone.com).
    AI/robotics/hardware news. Uses RSS feed.
    """
    articles = []
    try:
        response = httpx.get(
            "https://www.leiphone.com/feed",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)

        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            description = item.find("description")
            pub_date = item.find("pubDate")

            articles.append({
                "source": "leiphone",
                "title": title.text if title is not None else "",
                "url": link.text if link is not None else "",
                "content": description.text if description is not None else "",
                "published": pub_date.text if pub_date is not None else _now_iso(),
            })

    except Exception as e:
        print(f"[leiphone] Error fetching: {e}")

    return articles


def fetch_caixin() -> List[Dict]:
    """
    Fetch articles from Caixin (caixin.com).
    Premium China business/finance news.
    """
    articles = []
    seen_urls = set()
    try:
        response = httpx.get(
            "https://www.caixin.com/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for link_el in soup.select("a[href*='caixin.com/']")[:60]:
            url = link_el.get("href", "")
            # Filter for article URLs (typically contain date patterns like /2026-02-12/)
            if not url or url in seen_urls:
                continue
            if "/202" not in url:
                continue

            if not url.startswith("http"):
                url = "https://www.caixin.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = _safe_text(link_el)
            if not title or len(title) < 5:
                continue

            articles.append({
                "source": "caixin",
                "title": title[:200],
                "url": url,
                "content": "",
                "published": _now_iso(),
            })

            if len(articles) >= 25:
                break

    except Exception as e:
        print(f"[caixin] Error fetching: {e}")

    return articles


def fetch_jiemian() -> List[Dict]:
    """
    Fetch articles from Jiemian News (jiemian.com).
    Financial news aggregator.
    """
    articles = []
    seen_urls = set()
    try:
        response = httpx.get(
            "https://www.jiemian.com/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for link_el in soup.select("a[href*='/article/']")[:50]:
            url = link_el.get("href", "")
            if not url or url in seen_urls:
                continue

            if not url.startswith("http"):
                url = "https://www.jiemian.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = _safe_text(link_el)
            if not title or len(title) < 5:
                continue

            articles.append({
                "source": "jiemian",
                "title": title[:200],
                "url": url,
                "content": "",
                "published": _now_iso(),
            })

            if len(articles) >= 20:
                break

    except Exception as e:
        print(f"[jiemian] Error fetching: {e}")

    return articles


def fetch_zhidx() -> List[Dict]:
    """
    Fetch articles from Zhidx (zhidx.com).
    AI/hardware intelligence.
    """
    articles = []
    seen_urls = set()
    try:
        response = httpx.get(
            "https://zhidx.com/",
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for link_el in soup.select("a[href*='zhidx.com/p/']")[:50]:
            url = link_el.get("href", "")
            if not url or url in seen_urls:
                continue

            if not url.startswith("http"):
                url = "https://zhidx.com" + url

            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = _safe_text(link_el)
            if not title or len(title) < 5:
                continue

            articles.append({
                "source": "zhidx",
                "title": title[:200],
                "url": url,
                "content": "",
                "published": _now_iso(),
            })

            if len(articles) >= 20:
                break

    except Exception as e:
        print(f"[zhidx] Error fetching: {e}")

    return articles


def fetch_all_china_sources() -> Dict[str, List[Dict]]:
    """
    Fetch from all Tier 1 China sources.
    Returns dict mapping source name to list of articles.
    Continues with remaining sources if one fails.
    """
    results = {}

    scrapers = [
        ("36kr", fetch_36kr),
        ("huxiu", fetch_huxiu),
        ("infoq_china", fetch_infoq_china),
        ("csdn", fetch_csdn),
        ("sap_china", fetch_sap_china),
        ("kingdee", fetch_kingdee),
        ("yonyou", fetch_yonyou),
        ("leiphone", fetch_leiphone),
        ("caixin", fetch_caixin),
        ("jiemian", fetch_jiemian),
        ("zhidx", fetch_zhidx),
    ]

    for name, scraper in scrapers:
        try:
            articles = scraper()
            results[name] = articles
            print(f"[{name}] Fetched {len(articles)} articles")
        except Exception as e:
            print(f"[{name}] Failed: {e}")
            results[name] = []

    total = sum(len(articles) for articles in results.values())
    print(f"\nTotal: {total} articles from {len(results)} sources")

    return results


if __name__ == "__main__":
    # Test run
    import json

    print("Testing China source scrapers...\n")
    all_articles = fetch_all_china_sources()

    # Print sample from each source
    print("\n--- Sample Articles ---\n")
    for source, articles in all_articles.items():
        if articles:
            sample = articles[0]
            print(f"{source}:")
            print(f"  Title: {sample['title'][:60]}..." if len(sample['title']) > 60 else f"  Title: {sample['title']}")
            print(f"  URL: {sample['url']}")
            print()
