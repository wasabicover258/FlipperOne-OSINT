package main

import (
	"strings"
	"testing"
	"time"
)

// Tests for the modules ported from 2.0.x: IPv6, GLEIF/Wikidata, GPS/POI,
// Wayback snapshots. All offline with recorded or literal fixtures.

const (
	leiExample  = "5299000EXAMPLEAG0066"
	leiParent   = "5299000PARENTCO00081"
	leiUltimate = "5299000ULTIMATE00075"
)

func runOnly(t *testing.T, seed string, mods ...*Module) []Finding {
	t.Helper()
	f, err := seedFor(seed)
	if err != nil {
		t.Fatal(err)
	}
	e := &Engine{Modules: mods, MaxDepth: 4, Keys: map[string]string{}, Deadline: 20 * time.Second}
	return e.Run(f)
}

func TestIPHelpers(t *testing.T) {
	if canonicalIP("2001:DB8:0:0::1") != "2001:db8::1" || canonicalIP("[::ffff:192.0.2.1]") != "192.0.2.1" || canonicalIP("x") != "" {
		t.Error("canonicalIP")
	}
	if r := reverseName("192.0.2.1"); r != "1.2.0.192.in-addr.arpa" {
		t.Error(r)
	}
	if r := reverseName("2001:db8::1"); r != "1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa" {
		t.Error(r)
	}
	for ip, want := range map[string]bool{
		"8.8.8.8": true, "2606:4700:4700::1111": true, "10.1.2.3": false, "100.64.1.1": false, "fd00::1": false,
		"fe80::1": false, "2001:db8::1": false, "127.0.0.1": false, "192.0.2.1": false,
	} {
		if publicIP(ip) != want {
			t.Errorf("publicIP(%s) != %v", ip, want)
		}
	}
}

func TestAnalyzeIPv6(t *testing.T) {
	cases := []struct {
		ip, kind string
		emb      []string
		mac      string
	}{
		{"2002:c000:0204::1", "6to4", []string{"192.0.2.4"}, ""},
		{"2001:0000:4136:e378:8000:63bf:3fff:fdd2", "Teredo", []string{"65.54.227.120", "192.0.2.45"}, ""},
		{"64:ff9b::808:808", "NAT64 (well-known prefix)", []string{"8.8.8.8"}, ""},
		{"2a00:1450::211:22ff:fe33:4455", "global unicast", nil, "00:11:22:33:44:55"},
	}
	for _, c := range cases {
		r, ok := analyzeIPv6(c.ip)
		if !ok || r.Kind != c.kind || r.MAC != c.mac || len(r.Embedded) != len(c.emb) {
			t.Errorf("%s: %+v", c.ip, r)
			continue
		}
		for i, e := range c.emb {
			if r.Embedded[i].IP != e {
				t.Errorf("%s: embedded %d = %s, want %s", c.ip, i, r.Embedded[i].IP, e)
			}
		}
	}
	if _, ok := analyzeIPv6("8.8.8.8"); ok {
		t.Error("IPv4 analysed as IPv6")
	}
}

func TestIPv6DeepScan(t *testing.T) {
	fn := setupFake(t)
	const ip = "2606:4700:4700::1111"
	fn.dns[reverseName(ip)+" PTR"] = rr("PTR", "one.one.one.one.")
	fn.http["https://internetdb.shodan.io/"+ip] = `{"ports":[443,53],"cpes":[],"hostnames":[],"tags":[],"vulns":[]}`
	fn.http["https://stat.ripe.net/data/prefix-overview/data.json?resource="+ip] = `{"data":{"resource":"2606:4700::/32","asns":[{"asn":13335,"holder":"CLOUDFLARENET"}]}}`
	fn.http["https://stat.ripe.net/data/announced-prefixes"] = `{"data":{"prefixes":[{"prefix":"1.1.1.0/24"},{"prefix":"2606:4700::/32"}]}}`
	fn.http["https://ipwho.is/"+ip] = `{"ip":"2606:4700:4700::1111","success":true,"country":"United States","country_code":"US","city":"San Francisco","connection":{"asn":13335,"isp":"Cloudflare, Inc."},"timezone":{"id":"America/Los_Angeles"}}`

	fs := runOnly(t, "2606:4700:4700:0:0:0:0:1111", modDNS, modRDNS, modInternetDB, modRIPE, modASNPrefixes, modIPv6, modIPWhois)
	for _, w := range []struct {
		k Kind
		v string
	}{
		{KIP, ip}, {KPort, "[2606:4700:4700::1111]:443/tcp"}, {KHost, "one.one.one.one"}, {KASN, "AS13335"},
		{KNetblock, "2606:4700::/32"}, {KAttr, "IPv6 type: global unicast"}, {KAttr, "ISP: Cloudflare, Inc."},
		{KAttr, "Location estimate: San Francisco, United States"},
	} {
		if find(fs, w.k, w.v) == nil {
			t.Errorf("missing %s %s", w.k, w.v)
		}
	}
	if f := find(fs, KIssue, "AS13335 network size"); f == nil || !strings.Contains(f.Detail, "1 IPv4, 1 IPv6") || !strings.Contains(f.Detail, "65536 IPv6 /48s") {
		t.Errorf("v6 prefix count: %+v", f)
	}
	// private addresses never hit rate-limited APIs
	fn.hits = map[string]int{}
	runOnly(t, "fd00::1", modInternetDB, modRIPE, modIPWhois, modRDNS)
	if len(fn.hits) != 0 {
		t.Errorf("private IP was looked up: %v", fn.hits)
	}
}

func TestLEIAndSeeds(t *testing.T) {
	for _, l := range []string{leiExample, leiParent, leiUltimate} {
		if !validLEI(l) {
			t.Errorf("%s should be valid", l)
		}
	}
	if validLEI("5299000EXAMPLEAG0067") || validLEI("short") {
		t.Error("bad LEI accepted")
	}
	for in, want := range map[string]Kind{
		"48.137154, 11.575490": KGeo, "-33.86 151.21": KGeo, "org:Example AG": KOrg, "company: ACME  Corp": KOrg,
		"place:Marienplatz Munich": KPlace, "place:48.1,11.5": KGeo, leiExample: KLEI, "lei:" + strings.ToLower(leiExample): KLEI,
		"2001:db8::1": KIP, "example.com": KDomain,
	} {
		f, err := seedFor(in)
		if err != nil || f.Type != want {
			t.Errorf("%s: %v %v", in, f.Type, err)
		}
		if g, _ := seedFor(seedTarget(f)); g.Type != f.Type || g.Value != f.Value {
			t.Errorf("seedTarget round trip %q -> %q", in, seedTarget(f))
		}
	}
	if f, _ := seedFor("company: ACME  Corp"); f.Value != "ACME Corp" {
		t.Errorf("org name not normalised: %q", f.Value)
	}
	if _, err := seedFor("95.1,11"); err == nil {
		t.Error("latitude 95 accepted")
	}
}

func gleifRec(lei, name, city string) string {
	return `{"id":"` + lei + `","attributes":{"lei":"` + lei + `","entity":{"legalName":{"name":"` + name +
		`"},"status":"ACTIVE","jurisdiction":"DE","legalAddress":{"addressLines":["Main St 1"],"city":"` + city +
		`","country":"DE","postalCode":"80331"}},"registration":{"status":"ISSUED"}}}`
}

func TestOrgScan(t *testing.T) {
	fn := setupFake(t)
	g := "https://api.gleif.org/api/v1/lei-records"
	fn.http[g+"?filter%5Bentity.legalName%5D=Example+AG"] = `{"data":[` + gleifRec(leiExample, "Example AG", "Munich") + `]}`
	fn.http[g+"/"+leiExample] = `{"data":` + gleifRec(leiExample, "Example AG", "Munich") + `}`
	fn.http[g+"/"+leiExample+"/direct-parent"] = `{"data":` + gleifRec(leiParent, "Parent Holding GmbH", "Berlin") + `}`
	fn.http[g+"/"+leiExample+"/ultimate-parent"] = `{"data":` + gleifRec(leiUltimate, "Ultimate SE", "Paris") + `}`
	w := "https://www.wikidata.org/w/api.php?action="
	fn.http[w+"query"] = `{"query":{"search":[{"title":"Q123"}]}}`
	fn.http[w+"wbsearchentities"] = `{"search":[{"id":"Q123"},{"id":"Q999"}]}`
	fn.http[w+"wbgetentities"] = `{"entities":{
	  "Q123":{"labels":{"en":{"value":"Example AG"}},"claims":{"P856":[{"mainsnak":{"datavalue":{"value":"https://www.example-ag.com/en"}}}],"P1278":[{"mainsnak":{"datavalue":{"value":"` + leiExample + `"}}}]}},
	  "Q999":{"labels":{"en":{"value":"Example (film)"}},"claims":{}}}}`

	fs := runOnly(t, "org:Example AG", modGLEIF, modWikidataOrg, modDNS)
	l := find(fs, KLEI, leiExample)
	if l == nil || l.Confidence != 90 || l.Source != "gleif" || l.Data["also"] != "wikidata" || l.Data["jurisdiction"] != "DE" || !strings.Contains(l.Data["legal_address"], "Munich") {
		t.Fatalf("LEI: %+v", l)
	}
	if p := find(fs, KLEI, leiParent); p == nil || p.Data["relation"] != "direct parent" {
		t.Errorf("direct parent: %+v", p)
	}
	if p := find(fs, KLEI, leiUltimate); p == nil || p.Data["relation"] != "ultimate parent" {
		t.Errorf("ultimate parent: %+v", p)
	}
	d := find(fs, KDomain, "example-ag.com")
	if d == nil || d.Data["relation"] != "official website" {
		t.Fatalf("official website: %+v", d)
	}
	if find(fs, KURL, "https://www.wikidata.org/wiki/Q999") != nil {
		t.Error("non-organisation Wikidata hit reported")
	}
	for _, f := range fs {
		if f.Parent == "domain:example-ag.com" || f.Parent == "lei:"+strings.ToLower(leiParent) {
			t.Errorf("context entity was expanded: %+v", f)
		}
	}
	if !strings.Contains(strings.Join(pivotHints(fs), "|"), "deep example-ag.com") {
		t.Errorf("no pivot hint for the website: %v", pivotHints(fs))
	}

	// direct LEI input: record lookup, legal name and addresses as attributes
	fs = runOnly(t, leiExample, modGLEIF)
	if o := find(fs, KOrg, "Example AG"); o == nil || o.Confidence != 100 {
		t.Errorf("legal name: %+v", o)
	}
	if find(fs, KAttr, "legal address: Main St 1, 80331 Munich, DE") == nil {
		t.Errorf("legal address missing: %+v", fs)
	}
}

func pivotHints(fs []Finding) []string {
	var hs []string
	for _, p := range pivots(fs) {
		hs = append(hs, p.Hint)
	}
	return hs
}

const overpassFixture = `{"elements":[
 {"type":"node","id":1,"lat":48.1372,"lon":11.5756,"tags":{"amenity":"cafe","name":"Cafe Near","website":"https://www.cafe-near.de","phone":"+49 89 1"}},
 {"type":"way","id":2,"center":{"lat":48.1380,"lon":11.5760},"tags":{"amenity":"hospital","name":"City Hospital"}},
 {"type":"node","id":3,"lat":48.13801,"lon":11.57601,"tags":{"amenity":"hospital","name":"City Hospital","phone":"+49 89 2"}},
 {"type":"node","id":4,"lat":48.1373,"lon":11.5757,"tags":{"shop":"bakery"}},
 {"type":"node","id":5,"lat":48.1373,"lon":11.5757,"tags":{"building":"house","name":"Private"}},
 {"type":"node","id":6,"lat":48.20,"lon":11.60,"tags":{"amenity":"pharmacy","name":"Far Away"}}
]}`

func TestGeoScan(t *testing.T) {
	fn := setupFake(t)
	fn.http["https://nominatim.openstreetmap.org/search?"] = `[{"lat":"48.137154","lon":"11.575490","display_name":"Marienplatz, Munich, Germany","category":"place","type":"square"},
	  {"lat":"52.5","lon":"13.4","display_name":"Marienplatz, Berlin","category":"highway","type":"pedestrian"}]`
	fn.http["https://nominatim.openstreetmap.org/reverse?"] = `{"display_name":"Marienplatz 1, 80331 Munich, Germany","category":"building","type":"townhall","address":{"country_code":"de"}}`
	fn.http["https://api.open-meteo.com/"] = `{"elevation":519.0,"timezone":"Europe/Berlin","timezone_abbreviation":"CET","utc_offset_seconds":3600}`
	fn.http["https://overpass-api.de/"] = overpassFixture
	fn.http["https://en.wikipedia.org/w/api.php?"] = `{"query":{"geosearch":[{"pageid":42,"title":"Marienplatz","dist":12.5}]}}`

	fs := runOnly(t, "place:Marienplatz", modGeocode, modGeoLinks, modGeoMeta, modReverseGeo, modOverpass, modWikiGeo)
	for _, w := range []struct {
		k Kind
		v string
	}{
		{KGeo, "48.137154,11.575490"}, {KAttr, "Elevation: 519 m"}, {KAttr, "Time zone: Europe/Berlin"},
		{KAttr, "Nearest address: Marienplatz 1, 80331 Munich, Germany"}, {KAttr, "DMS: 48d08'13.8\"N 11d34'31.8\"E"},
		{KURL, "geo:48.137154,11.575490"}, {KURL, "https://en.wikipedia.org/?curid=42"},
		{KPlace, "Cafe Near (node/1)"}, {KDomain, "cafe-near.de"},
	} {
		if find(fs, w.k, w.v) == nil {
			t.Errorf("missing %s %s", w.k, w.v)
		}
	}
	if f := find(fs, KAttr, "Time zone: Europe/Berlin"); f == nil || f.Detail != "UTC+01:00 (CET)" {
		t.Errorf("tz detail: %+v", f)
	}
	var places []Finding
	for _, f := range fs {
		if f.Type == KPlace && f.Depth > 0 {
			places = append(places, f)
		}
	}
	// node 3 duplicates way 2; unnamed shop, private house and far pharmacy are dropped
	if len(places) != 2 {
		t.Fatalf("want 2 places, got %d: %+v", len(places), places)
	}
	if h := find(fs, KPlace, "City Hospital (way/2)"); h == nil || h.Data["phone"] != "+49 89 2" {
		t.Errorf("duplicate merge lost the phone: %+v", h)
	}
	// second Nominatim candidate is reported, not followed
	if find(fs, KGeo, "52.500000,13.400000") != nil {
		t.Error("second geocoding match was followed")
	}

	// nearest first, independent of category
	ps, err := parseNearby([]byte(overpassFixture), 48.137154, 11.575490, 500)
	if err != nil || len(ps) != 2 || ps[0].Name != "Cafe Near" || ps[1].Name != "City Hospital" {
		t.Errorf("order: %+v %v", ps, err)
	}

	// Overpass fallback: first server fails, second answers
	delete(fn.http, "https://overpass-api.de/")
	fn.http["https://overpass.private.coffee/"] = overpassFixture
	fs = runOnly(t, "48.137154,11.575490", modOverpass)
	if find(fs, KPlace, "Cafe Near (node/1)") == nil {
		t.Error("Overpass fallback not used")
	}
}

func TestWaybackSnapshots(t *testing.T) {
	fn := setupFake(t)
	c := "https://web.archive.org/cdx/search/cdx?url=example.com&output=json&fl=timestamp,original&filter=statuscode:200&limit="
	fn.http[c+"1"] = `[["timestamp","original"],["20020120142510","http://example.com/"]]`
	fn.http[c+"-1"] = `[["timestamp","original"],["20261101000000","https://example.com/"]]`
	fs := runOnly(t, "example.com", modArchive)
	if find(fs, KAttr, "First archived: 2002-01-20") == nil || find(fs, KAttr, "Latest archived: 2026-11-01") == nil ||
		find(fs, KURL, "https://web.archive.org/web/20020120142510/http://example.com/") == nil {
		t.Errorf("snapshots: %+v", fs)
	}
}

func TestDMS(t *testing.T) {
	if d := dms(-33.8688, 151.2093); d != "33d52'07.7\"S 151d12'33.5\"E" {
		t.Error(d)
	}
	if d := dms(10.9999999, -0.5); d != "11d00'00.0\"N 0d30'00.0\"W" {
		t.Error(d)
	}
}
