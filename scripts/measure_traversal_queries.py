"""Count SQL statements and payload sizes per tool call and per plan-hydration step.

Loads the real canonical CSVs into the sqlite-backed DB-API shim from
tests/test_postgres_store.py, so the statements counted are exactly the ones
PostgresCanonicalStore issues in production. Latency is not measured.

Run from the repo root:

    PYTHONPATH=. .venv/bin/python scripts/measure_traversal_queries.py

Companion to docs/graph-traversal-assessment-2026-09-21.md; rerun it after any
change to deadbot/postgres.py, deadbot/tools.py, deadbot/finish.py or
deadbot/composition.py and compare the numbers.
"""
import json, re, sys, time
sys.path.insert(0, "tests"); sys.path.insert(0, ".")
from test_postgres_store import Connection
from deadbot.data import CanonicalStore
from deadbot.postgres import PostgresCanonicalStore, query_cache_scope
from deadbot.tools import build_tools
from deadbot import finish, composition
from deadbot.finish import ShowUnitRef, SongOverviewRef, EraUnitRef, PerformanceUnitRef, PersonRosterRef, PersonRosterEntry

t0=time.time()
tables = CanonicalStore().tables
conn = Connection(tables)
print(f"loaded sqlite in {time.time()-t0:.1f}s", file=sys.stderr)
store = PostgresCanonicalStore(conn, schema="canonical")
tools = {t.name: t for t in build_tools(store)}

def tbl(sql):
    m = re.findall(r'"canonical"\."(\w+)"', sql); return m[0] if m else "?"

def run(label, name, args, cache=None):
    before = len(conn.statements)
    t=time.time()
    with query_cache_scope(cache):
        out = tools[name].invoke(args)
    issued = conn.statements[before:]
    tables_hit = {}
    for sql,_ in issued: tables_hit[tbl(sql)] = tables_hit.get(tbl(sql),0)+1
    full = sum(1 for sql,_ in issued if " WHERE " not in sql and "COUNT" not in sql)
    print(f"{label:60s} queries={len(issued):3d} full_table_scans={full:2d} chars={len(out):7d} ~tokens={len(out)//4:6d}  {dict(sorted(tables_hit.items(), key=lambda kv:-kv[1]))}")
    return json.loads(out), issued

print("\n=== Q1 Branford ===")
p,_ = run("search_entities(question)", "search_entities", {"query":"What shows did Branford Marsalis play with the Dead?"})
print("   matches:", [(m['entity_type'],m['id']) for m in p['matches']][:8])
g,_ = run("search_guest_musicians('Branford Marsalis')", "search_guest_musicians", {"query":"Branford Marsalis"})
shows = [a['show_id'] for a in g['guests'][0]['appearances']]
print("   shows:", shows)
cache={}
for s in shows:
    run(f"get_show({s})", "get_show", {"show_id_or_date": s}, cache)

print("\n=== Q2 Eyes of the World ===")
run("search_entities(question)", "search_entities", {"query":"How did Eyes of the World evolve over the decades?"})
cache={}
song,_ = run("get_song('Eyes of the World')", "get_song", {"song_id_or_title":"Eyes of the World"}, cache)
run("get_song_performance_profile", "get_song_performance_profile", {"song_id_or_title":"song-eyes-of-the-world"}, cache)
lp,_ = run("list_song_performances page1 (limit 24)", "list_song_performances", {"song_id_or_title":"song-eyes-of-the-world"}, cache)
print("   performance_count", lp['performance_count'], "pages@24:", -(-lp['performance_count']//24), "pages@48:", -(-lp['performance_count']//48))
run("list_song_performances page2 (fresh cache)", "list_song_performances", {"song_id_or_title":"song-eyes-of-the-world","offset":24})
nv,_ = run("get_song_notable_versions", "get_song_notable_versions", {"song_id_or_title":"song-eyes-of-the-world"}, cache)
print("   versions with a source:", nv['signal_summary'])
pids = [v['performance_id'] for v in nv['versions'][:6]]
for pid in pids[:3]:
    run(f"get_performance({pid})", "get_performance", {"performance_id": pid}, cache)

print("\n=== Q3 1981-03-09 ===")
cache={}
sh,_ = run("get_show('1981-03-09')", "get_show", {"show_id_or_date":"1981-03-09"}, cache)
print("   performances:", len(sh['performances']), "recordings:", sh['recordings']['count'], "performers:", len(sh['performers']), "show_links:", len(sh.get('show_links',[])), "official_releases:", len(sh.get('official_releases',[])))
run("get_media_links(show)", "get_media_links", {"entity_type":"show","entity_id":"gd-1981-03-09"}, cache)
run("get_performance(first song)", "get_performance", {"performance_id": sh['performances'][0]['performance_id']}, cache)
run("get_selections_for(show) [no selection table here]", "get_selections_for", {"entity_type":"show","entity_id_or_name":"gd-1981-03-09"}, cache)

print("\n=== Q4 most played 1977 ===")
p,_ = run("search_entities(question)", "search_entities", {"query":"Which songs were most frequently played in 1977?"})
print("   matches:", [(m['entity_type'],m['id']) for m in p['matches']][:20])

print("\n=== Q5 guests most often ===")
g,_ = run("search_guest_musicians('')", "search_guest_musicians", {"query":""})
print("   guest_count:", g['guest_count'], "top5:", [(x['name'],x['guest_show_count']) for x in g['guests'][:5]])

print("\n=== search_stored_resources ===")
run("search_stored_resources('Eyes of the World')", "search_stored_resources", {"query":"Eyes of the World"})

print("\n=== Plan hydration (finish.resolve_items) ===")
def hydrate(label, items, payloads, cache):
    grounded = finish.grounded_context(payloads)
    before = len(conn.statements)
    with query_cache_scope(cache):
        blocks, _ = finish.resolve_items(items, grounded, payloads, store)
    issued = conn.statements[before:]
    th={}
    for sql,_ in issued: th[tbl(sql)] = th.get(tbl(sql),0)+1
    print(f"{label:60s} queries={len(issued):3d} blocks={len(blocks)}  {dict(sorted(th.items(), key=lambda kv:-kv[1]))}")

# Branford: research payloads = guest search + 5 get_show, same cache carried (as api.py does)
cache={}
payloads=[]
with query_cache_scope(cache):
    payloads.append(json.loads(tools["search_guest_musicians"].invoke({"query":"Branford Marsalis"})))
    for s in shows: payloads.append(json.loads(tools["get_show"].invoke({"show_id_or_date": s})))
items=[ShowUnitRef(type="show_unit", show_id=s, emphasis="primary" if i==0 else "supporting", visible_facets=["guests","listen","setlist","lineup","recordings"]) for i,s in enumerate(shows)]
hydrate("5 show_units, warm cache (get_show called for each)", items, payloads, cache)
hydrate("5 show_units, cold cache (model never called get_show)", items, payloads, {})
hydrate("5 show_units, cold, facets=[guests,listen]", [ShowUnitRef(type="show_unit", show_id=s, visible_facets=["guests","listen"]) for s in shows], payloads, {})

# Eyes: song_overview + era units
cache={}
payloads=[]
with query_cache_scope(cache):
    payloads.append(json.loads(tools["get_song"].invoke({"song_id_or_title":"Eyes of the World"})))
    payloads.append(json.loads(tools["get_song_notable_versions"].invoke({"song_id_or_title":"song-eyes-of-the-world"})))
    payloads.append(json.loads(tools["list_song_performances"].invoke({"song_id_or_title":"song-eyes-of-the-world","limit":48})))
pids = [v['performance_id'] for v in payloads[1]['versions'][:12]]
items=[SongOverviewRef(type="song_overview", song_id="song-eyes-of-the-world", emphasis="primary", visible_facets=["representatives","history","credits","albums"], representative_performance_ids=pids[:3])]
hydrate("song_overview (all facets), warm", items, payloads, cache)
hydrate("song_overview (all facets), cold", items, payloads, {})
eras=[EraUnitRef(type="era_unit", title=f"era {i}", representative_performance_ids=pids[i*3:(i+1)*3]) for i in range(4)]
hydrate("4 era_units x 3 performances, warm", eras, payloads, cache)
hydrate("4 era_units x 3 performances, cold", eras, payloads, {})
hydrate("3 performance_units, cold", [PerformanceUnitRef(type="performance_unit", performance_id=p) for p in pids[:3]], payloads, {})

# Guests roster
cache={}
with query_cache_scope(cache):
    gp = json.loads(tools["search_guest_musicians"].invoke({"query":""}))
top = [g['person_id'] for g in gp['guests'][:40]]
hydrate("person_roster 40 people (from guest payload)", [PersonRosterRef(type="person_roster", title="Recurring guests", entries=[PersonRosterEntry(person_id=p) for p in top])], [gp], cache)

print("\n=== fixed prefix: tool schemas ===")
from langchain_core.utils.function_calling import convert_to_openai_tool
from deadbot.finish import build_finish_tool
total=0
for t in [*build_tools(store), build_finish_tool()]:
    n=len(json.dumps(convert_to_openai_tool(t))); total+=n
    if n>4000: print(f"   {t.name}: {n} chars")
print(f"   all tools: {total} chars ~{total//4} tokens")
