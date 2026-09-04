from deadbot.source_reader import (
    FetchedPage,
    PageReader,
    extract_page,
    focus_paragraphs,
    page_text,
    validate_url,
)


BLOGGER_PAGE = """<!DOCTYPE html><html><head><title>Lost Live Dead: Veneta 1972</title>
<meta property='og:title' content='Old Renaissance Faire Grounds, Veneta, August 27, 1972'/>
<meta name='description' content='A history of the Springfield Creamery benefit.'/>
<!--</head>--><body class='loading'>
<div class='navbar section' id='navbar'><a href='/'>Home</a> <a href='/search'>Search this blog</a></div>
<div class='post hentry'>
<h3 class='post-title entry-title'>Old Renaissance Faire Grounds, Veneta, August 27, 1972</h3>
<div class='post-header'><span class='post-timestamp'>at <abbr class='published' title='2012-08-27T09:00:00-07:00'>9:00 AM</abbr></span></div>
<div class='post-body entry-content' id='post-body-1'>
The Grateful Dead played a benefit for the Springfield Creamery on a very hot afternoon.<br/><br/>
Ken Kesey's family ran the creamery, and the show was filmed for what became Sunshine Daydream.
<br/><br/>The Dark Star that afternoon is one of the longest of the year, and the Bird Song is widely loved.
</div>
<div class='post-footer'><span class='post-author vcard'>Posted by <span class='fn'>Corry342</span></span>
<div class='post-share-buttons'>Share to Twitter</div></div>
</div>
<div class='comments' id='comments'><h4>7 comments:</h4><div class='comment'>I was there, it was hot. Best show ever.</div></div>
<div class='sidebar section' id='sidebar'><h2>Blog Archive</h2><ul><li>2012 (40)</li><li>2011 (52)</li></ul></div>
<div class='footer section'><p>Simple theme. Powered by Blogger.</p></div>
</body></html>"""

DRUPAL_PAGE = """<html><head><title>Greatest Stories Ever Told - Sugaree | Dead.net</title>
<meta property="article:published_time" content="2014-10-09T17:00:19-07:00" />
<meta name="author" content="David Dodd" /></head><body>
<header class="site-header"><nav><a href="/">Dead.net</a><a href="/band">Band</a></nav></header>
<main>
<article class="node node--type-feature">
<h1>Sugaree</h1>
<div class="field field--name-body">
<p>Hunter has said the song began under the working title Stingaree, after a rough patch of San Diego waterfront.</p>
<p>Live, the song stretched from a compact shuffle in 1971 into a fifteen-minute vehicle by 1977, when Garcia's solos built through three choruses.</p>
<p>The best-known version is probably the one from Cornell.</p>
</div>
</article>
<section class="comments"><article class="comment js-comment"><p>My favorite is 5/19/77. Fight me.</p></article></section>
</main>
<footer><p>Privacy policy. Terms of use.</p></footer>
</body></html>"""

NAV_ONLY_PAGE = """<html><head><title>Menu</title></head><body><nav><ul><li>Home</li><li>About</li></ul></nav><footer>Copyright</footer></body></html>"""


class FakeTransport:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> FetchedPage:
        self.calls.append(url)
        for key, page in self.pages.items():
            if key in url:
                return page
        return FetchedPage(404, url, "text/html", "")


def test_blogger_page_body_survives_commented_head_and_boilerplate_is_dropped():
    page = extract_page(BLOGGER_PAGE)
    assert page.title == "Old Renaissance Faire Grounds, Veneta, August 27, 1972"
    assert page.published.startswith("2012-08-27")
    assert page.byline == "Corry342"
    assert page.description == "A history of the Springfield Creamery benefit."
    text = page.text
    assert "Springfield Creamery" in text and "Sunshine Daydream" in text and "Bird Song" in text
    for boilerplate in ("Search this blog", "Share to Twitter", "Best show ever", "Blog Archive", "Powered by Blogger"):
        assert boilerplate not in text


def test_drupal_article_keeps_body_and_drops_comments_navigation_and_footer():
    page = extract_page(DRUPAL_PAGE)
    assert page.byline == "David Dodd"
    assert page.published.startswith("2014-10-09")
    assert "## Sugaree" in page.text
    assert "working title Stingaree" in page.text and "fifteen-minute vehicle" in page.text
    for boilerplate in ("Fight me", "Privacy policy", "Band"):
        assert boilerplate not in page.text


def test_navigation_only_page_has_no_paragraphs():
    assert extract_page(NAV_ONLY_PAGE).paragraphs == ()


def test_focus_returns_matching_passages_in_order_with_gap_markers():
    paragraphs = tuple(f"Paragraph {index} about something." for index in range(12))
    paragraphs = paragraphs[:5] + ("Here Garcia's solo builds through three choruses.",) + paragraphs[6:]
    text, matches = focus_paragraphs(paragraphs, "Garcia solo choruses", max_chars=400)
    assert matches == 1
    assert text.startswith("Paragraph 0")
    assert "[…]" in text
    assert "Garcia's solo" in text
    assert text.index("Paragraph 4") < text.index("Garcia's solo") < text.index("Paragraph 6")


def test_focus_with_no_match_reports_zero():
    assert focus_paragraphs(("alpha", "beta"), "gamma", 100) == ("", 0)


def test_paging_reconstructs_the_full_text_on_paragraph_boundaries():
    paragraphs = tuple(f"Paragraph number {index} " + "x" * 90 for index in range(10))
    full = "\n\n".join(paragraphs)
    pieces = []
    offset: int | None = 0
    while offset is not None:
        chunk, offset = page_text(paragraphs, offset, 300)
        pieces.append(chunk)
        assert chunk.startswith("Paragraph number") or chunk == ""
    assert "\n\n".join(piece.strip() for piece in pieces if piece) == full


def test_url_validation_rejects_non_http_and_local_addresses():
    assert validate_url("ftp://example.com/x")
    assert validate_url("https://localhost/x")
    assert validate_url("http://10.0.0.5/admin")
    assert validate_url("http://127.0.0.1:8000/")
    assert validate_url("https://lostlivedead.blogspot.com/2012/08/veneta.html") is None


def test_reader_returns_text_metadata_and_caches_the_fetch():
    transport = FakeTransport({"veneta.html": FetchedPage(200, "https://lostlivedead.blogspot.com/2012/08/veneta.html", "text/html; charset=utf-8", BLOGGER_PAGE)})
    reader = PageReader(transport)
    result = reader.read("https://lostlivedead.blogspot.com/2012/08/veneta.html")
    assert result.state == "ok"
    assert result.title.startswith("Old Renaissance")
    assert "Springfield Creamery" in result.text
    assert result.next_offset is None
    again = reader.read("https://lostlivedead.blogspot.com/2012/08/veneta.html", focus="Kesey creamery")
    assert again.focus_matches >= 1 and "Kesey" in again.text
    assert len(transport.calls) == 1


def test_reader_reports_http_failures_and_network_errors_without_raising():
    transport = FakeTransport({"missing": FetchedPage(404, "https://example.org/missing", "text/html", ""), "down": FetchedPage(0, "https://example.org/down", "", "")})
    reader = PageReader(transport)
    assert reader.read("https://example.org/missing").state == "unavailable"
    assert reader.read("https://example.org/down").state == "unavailable"
    assert reader.read("https://localhost/x").state == "invalid"
    assert not [call for call in transport.calls if "localhost" in call]


def test_reader_pretty_prints_json_and_pages_long_bodies():
    body = "{\"result\": [" + ", ".join(f"{{\"n\": {index}}}" for index in range(400)) + "]}"
    transport = FakeTransport({"api": FetchedPage(200, "https://archive.org/api", "application/json", body)})
    result = PageReader(transport).read("https://archive.org/api", max_chars=500)
    assert result.state == "ok" and result.text.startswith("{")
    assert result.next_offset is not None and result.total_chars > 500
