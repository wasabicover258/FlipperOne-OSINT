package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"encoding/xml"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

// fakeNet is a recorded-response world: DNS answers plus HTTP fixtures.
type fakeNet struct {
	dns  map[string][]dohAnswer // "name TYPE" -> answers
	nx   map[string]bool        // names that are NXDOMAIN
	http map[string]string      // URL prefix -> fixture file or literal body
	hits map[string]int
	mu   sync.Mutex
}

func (fn *fakeNet) fetch(ctx context.Context, u string, hdr map[string]string) (int, []byte, error) {
	fn.mu.Lock()
	fn.hits[u]++
	fn.mu.Unlock()
	if strings.Contains(u, "/resolve?") || strings.Contains(u, "/dns-query?") {
		q, _ := url.ParseQuery(u[strings.Index(u, "?")+1:])
		name, typ := q.Get("name"), q.Get("type")
		rep := dohReply{}
		if fn.nx[name] {
			rep.Status = 3
		}
		rep.Answer = fn.dns[name+" "+typ]
		b, _ := json.Marshal(rep)
		return 200, b, nil
	}
	// longest matching prefix wins (map order is random)
	best := ""
	for p := range fn.http {
		if strings.HasPrefix(u, p) && len(p) > len(best) {
			best = p
		}
	}
	if best == "" {
		return 404, nil, nil
	}
	v := fn.http[best]
	if strings.HasPrefix(v, "@") {
		b, err := os.ReadFile("testdata/" + v[1:])
		return 200, b, err
	}
	return 200, []byte(v), nil
}

func rr(t string, data ...string) []dohAnswer {
	var out []dohAnswer
	for _, d := range data {
		out = append(out, dohAnswer{Type: dnsTypeNum[t], Data: d})
	}
	return out
}

func setupFake(t *testing.T) *fakeNet {
	t.Helper()
	tmp := t.TempDir()
	t.Setenv("XDG_DATA_HOME", tmp)
	t.Setenv("XDG_CONFIG_HOME", tmp)
	t.Setenv("XDG_CACHE_HOME", tmp)
	noCache = true
	kevOnce = syncOnceReset()
	fn := &fakeNet{
		dns: map[string][]dohAnswer{
			"example.com A":          rr("A", "93.184.216.34"),
			"example.com MX":         rr("MX", "10 mail.example.com."),
			"www.example.com A":      rr("A", "93.184.216.34"),
			"shop.example.com CNAME": rr("CNAME", "example-shop.github.io."),
			"exarnple.com NS":        rr("NS", "ns1.parking.test."),
			"exarnple.com A":         rr("A", "203.0.113.9"),
			"exarnple.com MX":        rr("MX", "10 mx.parking.test."),
		},
		nx: map[string]bool{"example-shop.github.io": true},
		http: map[string]string{
			"https://crt.sh/":                                      "@crtsh_example.json",
			"https://internetdb.shodan.io/93.184.":                 "@internetdb_93.json",
			"https://www.cisa.gov/":                                "@kev_min.json",
			"https://stat.ripe.net/data/prefix-overview":           "@ripe_prefix.json",
			"https://api.first.org/data/v1/epss?cve=CVE-2020-0001": `{"data":[{"cve":"CVE-2020-0001","epss":"0.02"}]}`,
			"https://api.first.org/":                               `{"data":[{"epss":"0.97"}]}`,
		},
		hits: map[string]int{},
	}
	old, oldTLS := fetch, tlsDial
	fetch = fn.fetch
	tlsDial = func(ctx context.Context, host string, cfg *tls.Config) (*tls.ConnectionState, error) {
		return nil, errors.New("offline")
	}
	t.Cleanup(func() { fetch, tlsDial = old, oldTLS })
	return fn
}

func find(fs []Finding, typ Kind, value string) *Finding {
	for i := range fs {
		if fs[i].Type == typ && strings.EqualFold(fs[i].Value, value) {
			return &fs[i]
		}
	}
	return nil
}

func TestDeepScanWithFixtures(t *testing.T) {
	setupFake(t)
	maxLookalikeChecks = 5000
	e := &Engine{Modules: allModules(), MaxDepth: 4, Keys: map[string]string{}, Deadline: 30 * time.Second}
	fs := e.Run(Finding{Type: KDomain, Value: "example.com"})

	for _, want := range []struct {
		k Kind
		v string
	}{
		{KHost, "www.example.com"}, {KHost, "dev.example.com"}, {KHost, "shop.example.com"},
		{KHost, "mail.example.com"}, {KIP, "93.184.216.34"}, {KPort, "93.184.216.34:443/tcp"},
		{KCVE, "CVE-2021-41773"}, {KASN, "AS15133"}, {KNetblock, "93.184.216.0/24"},
		{KLookalike, "exarnple.com"},
	} {
		if find(fs, want.k, want.v) == nil {
			t.Errorf("missing %s %s", want.k, want.v)
		}
	}
	if find(fs, KHost, "evil.other.org") != nil {
		t.Error("out-of-domain crt.sh name leaked into results")
	}
	// takeover: CNAME to unclaimed GitHub Pages
	to := find(fs, KIssue, "Subdomain takeover: shop.example.com")
	if to == nil || to.Severity < SevHigh {
		t.Fatalf("takeover not detected: %+v", to)
	}
	// KEV CVE must be critical, low-EPSS CVE low
	if f := find(fs, KIssue, "CVE-2021-41773 on 93.184.216.34"); f == nil || f.Severity != SevCritical {
		t.Errorf("KEV CVE not critical: %+v", f)
	}
	if f := find(fs, KIssue, "CVE-2020-0001 on 93.184.216.34"); f == nil || f.Severity != SevLow {
		t.Errorf("low EPSS CVE wrong: %+v", f)
	}
	if f := find(fs, KLookalike, "exarnple.com"); f.Severity != SevHigh {
		t.Errorf("lookalike with MX should be high, got %s", f.Severity)
	}
	// unrelated hostname from InternetDB is recorded but not expanded
	if f := find(fs, KHost, "unrelated.net"); f == nil {
		t.Error("internetdb hostname missing")
	}
	for _, f := range fs {
		if f.Parent == "hostname:unrelated.net" {
			t.Errorf("out-of-scope host was expanded: %+v", f)
		}
	}
	s := summarize(fs)
	if s.Counts[SevCritical] < 1 || s.Counts[SevHigh] < 2 || s.Grade != "F" {
		t.Errorf("summary %+v", s)
	}
}

func TestEngineDepthDedupAndRetry(t *testing.T) {
	calls := 0
	flaky := &Module{Name: "flaky", In: []Kind{KDomain}, Retries: 2,
		Run: func(ctx context.Context, in Finding, out *Out) error {
			calls++
			if calls < 2 {
				return errors.New("HTTP 503")
			}
			out.Add(Finding{Type: KHost, Value: "a." + in.Value})
			out.Add(Finding{Type: KHost, Value: "a." + in.Value}) // duplicate
			return nil
		}}
	chain := &Module{Name: "chain", In: []Kind{KHost},
		Run: func(ctx context.Context, in Finding, out *Out) error {
			out.Add(Finding{Type: KHost, Value: "x." + in.Value})
			return nil
		}}
	slow := &Module{Name: "slow", In: []Kind{KDomain}, Timeout: 50 * time.Millisecond,
		Run: func(ctx context.Context, in Finding, out *Out) error {
			<-ctx.Done()
			return ctx.Err()
		}}
	e := &Engine{Modules: []*Module{flaky, chain, slow}, MaxDepth: 3, Deadline: 10 * time.Second}
	start := time.Now()
	fs := e.Run(Finding{Type: KDomain, Value: "t.test"})
	if time.Since(start) > 5*time.Second {
		t.Error("slow module blocked the run")
	}
	if calls != 2 {
		t.Errorf("retry: %d calls", calls)
	}
	n := 0
	for _, f := range fs {
		if f.Type == KHost {
			n++
		}
	}
	// a.t.test (1), x.a.t.test (2), x.x.a.t.test (3, not expanded)
	if n != 3 {
		t.Errorf("want 3 hosts within depth, got %d: %+v", n, fs)
	}
	if e.Errors["slow"] != 1 {
		t.Errorf("slow module error not counted: %v", e.Errors)
	}
}

func TestKeyedModulesLocked(t *testing.T) {
	e := &Engine{Keys: map[string]string{}}
	if e.Enabled(modVTSubs) {
		t.Error("VirusTotal enabled without key")
	}
	e.Keys["VIRUSTOTAL_API_KEY"] = "x"
	if !e.Enabled(modVTSubs) {
		t.Error("VirusTotal locked with key")
	}
	m := map[string]string{}
	dir := t.TempDir()
	os.WriteFile(dir+"/k.env", []byte("# c\nexport SHODAN_API_KEY=\"abc\"\nEMPTY=\n"), 0o600)
	parseEnvFile(dir+"/k.env", m)
	if m["SHODAN_API_KEY"] != "abc" || len(m) != 1 {
		t.Errorf("parse: %v", m)
	}
}

func TestTakeoverVerdict(t *testing.T) {
	gh := matchTakeover("foo.github.io.")
	if gh == nil || gh.Service != "GitHub Pages" {
		t.Fatalf("match: %+v", gh)
	}
	if s, _ := takeoverVerdict(gh, false, []byte("<h1>There isn't a GitHub Pages site here.</h1>")); s != SevCritical {
		t.Errorf("fingerprint: %s", s)
	}
	if s, _ := takeoverVerdict(gh, false, []byte("normal site")); s != SevInfo {
		t.Errorf("live site flagged: %s", s)
	}
	az := matchTakeover("app.azurewebsites.net")
	if s, _ := takeoverVerdict(az, true, nil); s != SevCritical {
		t.Errorf("azure nx: %s", s)
	}
	if s, _ := takeoverVerdict(nil, true, nil); s != SevMedium {
		t.Errorf("generic dangling: %s", s)
	}
	if matchTakeover("www.example.com") != nil {
		t.Error("false match")
	}
}

func TestLookalikes(t *testing.T) {
	c := lookalikes("wempe.de")
	for d, tech := range map[string]string{
		"wempe.com": "tld-swap", "wmpe.de": "omission", "wemep.de": "transposition",
		"wernpe.de": "homoglyph", "wempee.de": "repetition", "wem-pe.de": "hyphenation",
	} {
		if c[d] != tech {
			t.Errorf("%s: want %s got %q", d, tech, c[d])
		}
	}
	if _, ok := c["wempe.de"]; ok {
		t.Error("original included")
	}
	idn := 0
	for d, tech := range c {
		if tech == "homoglyph-idn" {
			idn++
			if !strings.HasPrefix(d, "xn--") {
				t.Errorf("idn not punycoded: %s", d)
			}
		}
	}
	if idn == 0 {
		t.Error("no IDN homoglyphs")
	}
	if len(lookalikes("example.co.uk")) == 0 || lookalikes("example.co.uk")["exampl.co.uk"] != "omission" {
		t.Error("multi-label suffix not handled")
	}
}

func TestPunycode(t *testing.T) {
	for in, want := range map[string]string{
		"münchen": "xn--mnchen-3ya", "bücher": "xn--bcher-kva", "example": "example", "раураl": "xn--l-7sba6dbr",
	} {
		if got, _ := punyLabel(in); got != want {
			t.Errorf("%s: got %s want %s", in, got, want)
		}
	}
}

func TestRegistrableDomain(t *testing.T) {
	for in, want := range map[string]string{
		"a.b.example.com": "example.com", "www.bbc.co.uk": "bbc.co.uk", "foo.github.io": "foo.github.io",
		"co.uk": "", "example.de.": "example.de",
	} {
		if got := registrableDomain(in); got != want {
			t.Errorf("%s: got %q want %q", in, got, want)
		}
	}
}

func TestSeedDetection(t *testing.T) {
	for in, want := range map[string]Kind{
		"8.8.8.8": KIP, "2001:db8::1": KIP, "as15169": KASN, "cve-2021-44228": KCVE,
		"https://Example.com/path": KDomain, "mail.example.com": KHost,
	} {
		f, err := seedFor(in)
		if err != nil || f.Type != want {
			t.Errorf("%s: %v %v", in, f.Type, err)
		}
	}
	if _, err := seedFor("not a target"); err == nil {
		t.Error("garbage accepted")
	}
}

func TestDiffAndWatch(t *testing.T) {
	setupFake(t)
	old := []Finding{{Type: KDomain, Value: "e.com"}, {Type: KHost, Value: "a.e.com", Depth: 1}, {Type: KPort, Value: "1.2.3.4:22/tcp", Depth: 3}}
	cur := []Finding{{Type: KDomain, Value: "e.com"}, {Type: KHost, Value: "A.e.com", Depth: 1}, {Type: KHost, Value: "new.e.com", Depth: 1},
		{Type: KLookalike, Value: "e-login.com", Depth: 1, Severity: SevHigh}}
	d := diffRuns(old, cur)
	if len(d.Added) != 2 || len(d.Removed) != 1 || d.Added[0].Value != "e-login.com" {
		t.Errorf("diff %+v", d)
	}
	if ok, _ := watchAdd("e.com"); !ok {
		t.Error("add")
	}
	if ok, _ := watchAdd("E.com"); ok {
		t.Error("duplicate add")
	}
	if len(loadWatch()) != 1 {
		t.Error("list")
	}
	c, err := saveRun("e.com", KDomain, Run{Findings: old})
	if err != nil || len(c.Runs) != 1 {
		t.Fatal(err)
	}
	for i := 0; i < keepRuns+3; i++ {
		c, _ = saveRun("e.com", KDomain, Run{Findings: cur})
	}
	if len(c.Runs) != keepRuns {
		t.Errorf("runs kept %d", len(c.Runs))
	}
}

func TestExports(t *testing.T) {
	run := Run{Started: time.Now(), Findings: []Finding{
		{Type: KDomain, Value: "e.com"},
		{Type: KHost, Value: "a.e.com", Parent: "domain:e.com", Depth: 1},
		{Type: KIssue, Value: "Exposed .git repository: a.e.com", Parent: "hostname:a.e.com", Severity: SevCritical, Detail: "x|y"},
	}}
	c := &Case{Target: "e.com"}
	var b bytes.Buffer
	if err := exportGraphML(&b, run); err != nil {
		t.Fatal(err)
	}
	var g graphML
	if err := xml.Unmarshal(b.Bytes(), &g); err != nil || len(g.Graph.Nodes) != 3 || len(g.Graph.Edges) != 2 {
		t.Errorf("graphml: %v %d %d", err, len(g.Graph.Nodes), len(g.Graph.Edges))
	}
	b.Reset()
	exportMarkdown(&b, c, run)
	if !strings.Contains(b.String(), "x\\|y") || !strings.Contains(b.String(), "Grade") {
		t.Errorf("md: %s", b.String())
	}
	b.Reset()
	exportCSV(&b, run)
	if strings.Count(b.String(), "\n") != 4 {
		t.Errorf("csv: %s", b.String())
	}
	b.Reset()
	if err := exportJSON(&b, c, run); err != nil || !strings.Contains(b.String(), `"severity": "critical"`) {
		t.Errorf("json: %v %s", err, b.String())
	}
}

func TestExposureHit(t *testing.T) {
	env := exposureProbes[1]
	if !exposureHit(env, 200, []byte("DB_PASSWORD=secret\n")) {
		t.Error(".env not detected")
	}
	if exposureHit(env, 200, []byte("<!DOCTYPE html><a href=x?a=b>")) {
		t.Error("html page flagged as .env")
	}
	if exposureHit(exposureProbes[0], 404, []byte("ref: refs/heads/main")) {
		t.Error("404 flagged")
	}
}

func TestCertIssues(t *testing.T) {
	now := time.Now()
	soon := certIssues("h", fakeCert(now.Add(5*day)), nil, now)
	if len(soon) != 1 || soon[0].Severity != SevMedium {
		t.Errorf("soon: %+v", soon)
	}
	exp := certIssues("h", fakeCert(now.Add(-day)), fmt.Errorf("x"), now)
	if len(exp) != 1 || exp[0].Severity != SevHigh {
		t.Errorf("expired: %+v", exp)
	}
}

func TestScopeForNonDomainSeeds(t *testing.T) {
	var expanded []string
	probe := &Module{Name: "probe", In: []Kind{KHost, KDomain, KASN},
		Run: func(ctx context.Context, in Finding, out *Out) error {
			expanded = append(expanded, in.Value)
			return nil
		}}
	src := &Module{Name: "src", In: []Kind{KIP},
		Run: func(ctx context.Context, in Finding, out *Out) error {
			out.Add(Finding{Type: KHost, Value: "www.someone-else.com"})
			out.Add(Finding{Type: KASN, Value: "AS1", Data: map[string]string{"relation": "upstream"}})
			out.Add(Finding{Type: KASN, Value: "AS2"})
			return nil
		}}
	e := &Engine{Modules: []*Module{src, probe}, Workers: 1}
	e.Run(Finding{Type: KIP, Value: "192.0.2.1"})
	if len(expanded) != 1 || expanded[0] != "AS2" {
		t.Errorf("expanded %v, want only AS2", expanded)
	}
}
