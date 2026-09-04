import json

from deadbot.site_search import SiteSearcher, load_sites, resolve_site
from deadbot.source_reader import FetchedPage


class FakeTransport:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> FetchedPage:
        self.calls.append(url)
        for key, page in self.pages.items():
            if key in url:
                return page
        return FetchedPage(404, url, "text/html", "not found")


def _json_page(url: str, document) -> FetchedPage:
    return FetchedPage(200, url, "application/json", json.dumps(document))


BLOGGER_FEED = {
    "feed": {
        "openSearch$totalResults": {"$t": "3"},
        "entry": [
            {
                "title": {"$t": "Old Renaissance Faire Grounds, Veneta, August 27, 1972"},
                "published": {"$t": "2012-08-27T09:00:00.000-07:00"},
                "link": [{"rel": "self", "href": "https://www.blogger.com/feeds/x"}, {"rel": "alternate", "href": "https://lostlivedead.blogspot.com/2012/08/veneta.html"}],
                "content": {"$t": "<p>The Grateful Dead played a benefit for the <b>Springfield Creamery</b> in Veneta on a very hot afternoon.</p>"},
                "author": [{"name": {"$t": "Corry342"}}],
            }
        ],
    }
}


def test_directory_loads_and_resolves_names_aliases_and_hosts():
    sites = load_sites()
    assert resolve_site("Lost Live Dead", sites)["site_id"] == "lost-live-dead"
    assert resolve_site("https://www.lostlivedead.blogspot.com/2012/x.html", sites)["site_id"] == "lost-live-dead"
    assert resolve_site("gdao", sites)["search"]["method"] == "omeka_api"
    assert resolve_site("archive.org", sites)["search"]["method"] == "archive_search"
    assert resolve_site("unknown-site.example", sites) is None


def test_blogger_feed_search_returns_hits_with_snippet_date_and_author():
    transport = FakeTransport({"feeds/posts/default": _json_page("https://lostlivedead.blogspot.com/feeds/posts/default", BLOGGER_FEED)})
    result = SiteSearcher(transport).search("lost live dead", "Veneta creamery")
    assert result.state == "ok" and result.method == "blogger_feed" and result.total == 3
    hit = result.hits[0]
    assert hit.url == "https://lostlivedead.blogspot.com/2012/08/veneta.html"
    assert hit.published == "2012-08-27"
    assert "Springfield Creamery" in hit.snippet and "<b>" not in hit.snippet
    assert hit.extra["author"] == "Corry342"
    assert "q=Veneta+creamery" in transport.calls[0]


def test_omeka_api_search_builds_public_item_urls():
    items = [{"o:id": 38378, "o:title": "SAVE THE CREAMERY!! A field trip account", "dcterms:description": [{"@value": "Big open field. Hot as freaking hell."}], "dcterms:created": [{"@value": "2013-04-07"}]}]
    transport = FakeTransport({"/api/items": _json_page("https://www.gdao.org/api/items", items)})
    result = SiteSearcher(transport).search("gdao", "veneta")
    assert result.state == "ok"
    assert result.hits[0].url == "https://www.gdao.org/items/show/38378"
    assert "Hot as freaking hell" in result.hits[0].snippet
    assert result.hits[0].published == "2013-04-07"


def test_archive_search_by_date_and_by_text():
    docs = {"response": {"numFound": 23, "docs": [{"identifier": "gd77-05-08.sbd.hicks.4982.sbeok.shnf", "title": "Grateful Dead Live at Barton Hall on 1977-05-08", "date": "1977-05-08T00:00:00Z", "avg_rating": 4.79, "num_reviews": 299, "downloads": 1454839, "source": "Matrix (see notes)"}]}}
    transport = FakeTransport({"advancedsearch.php": _json_page("https://archive.org/advancedsearch.php", docs)})
    result = SiteSearcher(transport).search("archive.org", "1977-05-08")
    assert result.state == "ok" and result.total == 23
    assert "date%3A1977-05-08" in transport.calls[0]
    hit = result.hits[0]
    assert hit.url == "https://archive.org/details/gd77-05-08.sbd.hicks.4982.sbeok.shnf"
    assert hit.extra["avg_rating"] == 4.79 and hit.extra["num_reviews"] == 299
    SiteSearcher(transport).search("internet archive", "Cornell Barton Hall")
    assert "collection%3AGratefulDead%20AND%20%28Cornell%20Barton%20Hall%29" in transport.calls[1]


def test_sitemap_search_follows_an_index_and_matches_slugs():
    index = "<sitemapindex><sitemap><loc>https://deadheadhigh.com/sitemap-guides.xml</loc></sitemap></sitemapindex>"
    guides = "<urlset><url><loc>https://deadheadhigh.com/guides/how-grateful-dead-songs-changed-live</loc></url><url><loc>https://deadheadhigh.com/guides/best-first-grateful-dead-live-show</loc></url><url><loc>https://deadheadhigh.com/privacy</loc></url></urlset>"
    transport = FakeTransport({"sitemap-guides.xml": FetchedPage(200, "", "application/xml", guides), "sitemap.xml": FetchedPage(200, "", "application/xml", index)})
    result = SiteSearcher(transport).search("deadhead high", "how songs changed live")
    assert result.state == "ok" and result.method == "sitemap"
    assert result.hits[0].url.endswith("how-grateful-dead-songs-changed-live")
    assert all("privacy" not in hit.url for hit in result.hits)


def test_site_without_search_is_reported_as_unsupported_with_guidance():
    result = SiteSearcher(FakeTransport({})).search("dead.net", "sugaree")
    assert result.state == "unsupported" and "read_page" in result.message


def test_unknown_host_is_probed_and_falls_back_to_its_sitemap():
    sitemap = "<urlset><url><loc>https://example-dead-blog.org/posts/dark-star-1972-veneta</loc></url></urlset>"
    transport = FakeTransport({"sitemap.xml": FetchedPage(200, "", "application/xml", sitemap)})
    result = SiteSearcher(transport).search("example-dead-blog.org", "dark star veneta")
    assert result.state == "ok" and result.method == "sitemap"
    assert any("wp-json" in call for call in transport.calls) and any("feeds/posts" in call for call in transport.calls)


def test_invalid_queries_and_sites_are_rejected_without_network():
    transport = FakeTransport({})
    assert SiteSearcher(transport).search("lost live dead", "   ").state == "invalid"
    assert SiteSearcher(transport).search("not a host", "veneta").state == "invalid"
    assert transport.calls == []


def test_archive_reviews_and_ratings():
    reviews = {"result": [
        {"reviewbody": "Short.", "reviewtitle": "Meh", "reviewer": "a", "reviewdate": "2011-01-11 15:59:54", "stars": "3"},
        {"reviewbody": "The Scarlet>Fire here is the reason people talk about this night; Garcia's tone is glassy and the mix is perfect.", "reviewtitle": "Essential", "reviewer": "b", "reviewdate": "2015-05-08 10:00:00", "stars": "5"},
        {"reviewbody": "Fixed the shnid.", "reviewtitle": "New source info", "reviewer": "c", "reviewdate": "2011-01-11 15:59:54", "stars": "0"},
    ]}
    ratings = {"response": {"docs": [{"identifier": "gd77-05-08.sbd.hicks.4982.sbeok.shnf", "avg_rating": 4.79, "num_reviews": 299, "downloads": 1, "source": "Matrix"}]}}
    transport = FakeTransport({"/reviews": _json_page("", reviews), "advancedsearch.php": _json_page("", ratings)})
    searcher = SiteSearcher(transport)
    result = searcher.archive_reviews("gd77-05-08.sbd.hicks.4982.sbeok.shnf", limit=2)
    assert result["state"] == "ok" and result["review_count"] == 3
    assert result["reviews"][0]["title"] == "Essential" and result["reviews"][0]["stars"] == 5
    assert result["stars_histogram"] == {"5": 1, "3": 1}
    assert len(result["reviews"]) == 2
    assert searcher.archive_ratings(["gd77-05-08.sbd.hicks.4982.sbeok.shnf"])["gd77-05-08.sbd.hicks.4982.sbeok.shnf"]["avg_rating"] == 4.79
    assert searcher.archive_reviews("../etc/passwd")["state"] == "invalid"
