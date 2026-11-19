package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Shodan InternetDB (free): ports, CPEs, CVEs without scanning ourselves.
// ---------------------------------------------------------------------------

type internetDB struct {
	Ports     []int    `json:"ports"`
	Cpes      []string `json:"cpes"`
	Hostnames []string `json:"hostnames"`
	Tags      []string `json:"tags"`
	Vulns     []string `json:"vulns"`
}

func emitHostData(out *Out, ip, source string, r internetDB) {
	for _, p := range r.Ports {
		out.Add(Finding{Type: KPort, Value: ip + ":" + strconv.Itoa(p) + "/tcp", Source: source, Confidence: 75})
	}
	for _, c := range r.Cpes {
		out.Add(Finding{Type: KCPE, Value: c, Source: source, Confidence: 70, Detail: "on " + ip})
	}
	for _, v := range r.Vulns {
		out.Add(Finding{Type: KCVE, Value: strings.ToUpper(v), Source: source, Confidence: 60,
			Detail: "reported for " + ip + " (version-based, unverified)", Data: map[string]string{"ip": ip}})
	}
	for _, h := range r.Hostnames {
		out.Add(Finding{Type: KHost, Value: strings.ToLower(h), Source: source, Confidence: 60, Detail: "seen on " + ip})
	}
	for _, t := range r.Tags {
		sev := SevInfo
		if t == "compromised" || t == "malware" || t == "c2" {
			sev = SevHigh
		}
		if sev > SevInfo {
			out.Add(Finding{Type: KIssue, Value: "Host tagged '" + t + "': " + ip, Severity: sev, Source: source,
				Data: map[string]string{"check": "reputation", "ip": ip}})
		}
	}
}

var modInternetDB = &Module{
	Name: "internetdb", Desc: "Shodan InternetDB: ports, CPEs, CVEs (free)",
	In: []Kind{KIP}, Out: []Kind{KPort, KCPE, KCVE, KHost, KIssue}, Timeout: 15 * time.Second, Retries: 2, Rate: 300 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r internetDB
		err := getJSON(ctx, "https://internetdb.shodan.io/"+in.Value, nil, 12*time.Hour, &r)
		if err != nil {
			return err
		}
		emitHostData(out, in.Value, "internetdb", r)
		return nil
	},
}

var modShodanHost = &Module{
	Name: "shodan", Desc: "Shodan host API (full data)", Key: "SHODAN_API_KEY",
	In: []Kind{KIP}, Out: []Kind{KPort, KCPE, KCVE, KHost}, Timeout: 20 * time.Second, Rate: time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			Ports     []int    `json:"ports"`
			Hostnames []string `json:"hostnames"`
			Tags      []string `json:"tags"`
			Vulns     []string `json:"vulns"`
			Data      []struct {
				Cpe23 []string `json:"cpe23"`
			} `json:"data"`
		}
		u := "https://api.shodan.io/shodan/host/" + in.Value + "?key=" + out.eng.Keys["SHODAN_API_KEY"]
		if err := getJSON(ctx, u, nil, 12*time.Hour, &r); err != nil {
			return err
		}
		db := internetDB{Ports: r.Ports, Hostnames: r.Hostnames, Tags: r.Tags, Vulns: r.Vulns}
		for _, d := range r.Data {
			db.Cpes = append(db.Cpes, d.Cpe23...)
		}
		emitHostData(out, in.Value, "shodan", db)
		return nil
	},
}

// ---------------------------------------------------------------------------
// RIPEstat: IP -> ASN + prefix, ASN -> all announced prefixes + neighbours.
// ---------------------------------------------------------------------------

var modRIPE = &Module{
	Name: "ripestat", Desc: "IP -> ASN and routed prefix (RIPEstat/BGP)",
	In: []Kind{KIP}, Out: []Kind{KASN, KNetblock}, Timeout: 20 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			Data struct {
				Resource string `json:"resource"`
				ASNs     []struct {
					ASN    int    `json:"asn"`
					Holder string `json:"holder"`
				} `json:"asns"`
			} `json:"data"`
		}
		if err := getJSON(ctx, "https://stat.ripe.net/data/prefix-overview/data.json?resource="+in.Value, nil, 7*day, &r); err != nil {
			return err
		}
		if r.Data.Resource != "" && strings.Contains(r.Data.Resource, "/") {
			out.Add(Finding{Type: KNetblock, Value: r.Data.Resource, Source: "ripestat", Confidence: 95, Detail: "routed prefix of " + in.Value})
		}
		for _, a := range r.Data.ASNs {
			out.Add(Finding{Type: KASN, Value: "AS" + strconv.Itoa(a.ASN), Source: "ripestat", Confidence: 95,
				Detail: a.Holder, Data: map[string]string{"holder": a.Holder}})
		}
		return nil
	},
}

var modASNPrefixes = &Module{
	Name: "asn-prefixes", Desc: "ASN -> announced prefixes, upstreams, peers, size",
	In: []Kind{KASN}, Out: []Kind{KNetblock, KASN}, Timeout: 30 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		asn := strings.TrimPrefix(strings.ToUpper(in.Value), "AS")
		var pr struct {
			Data struct {
				Prefixes []struct {
					Prefix string `json:"prefix"`
				} `json:"prefixes"`
			} `json:"data"`
		}
		if err := getJSON(ctx, "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS"+asn, nil, 7*day, &pr); err != nil {
			return err
		}
		var v4 uint64
		for i, p := range pr.Data.Prefixes {
			if _, n, err := net.ParseCIDR(p.Prefix); err == nil && n.IP.To4() != nil {
				ones, _ := n.Mask.Size()
				v4 += 1 << (32 - ones)
			}
			if i < 200 {
				out.Add(Finding{Type: KNetblock, Value: p.Prefix, Source: "ripestat", Confidence: 90, Detail: "announced by AS" + asn})
			}
		}
		out.Add(Finding{Type: KIssue, Value: fmt.Sprintf("AS%s network size", asn), Severity: SevInfo, Source: "ripestat",
			Detail: fmt.Sprintf("%d prefixes, %d IPv4 addresses", len(pr.Data.Prefixes), v4),
			Data:   map[string]string{"check": "asn"}})

		var nb struct {
			Data struct {
				Neighbours []struct {
					ASN  int    `json:"asn"`
					Type string `json:"type"` // left = upstream, right = downstream
				} `json:"neighbours"`
			} `json:"data"`
		}
		if getJSON(ctx, "https://stat.ripe.net/data/asn-neighbours/data.json?resource=AS"+asn, nil, 7*day, &nb) == nil {
			for i, n := range nb.Data.Neighbours {
				if i >= 30 {
					break
				}
				rel := map[string]string{"left": "upstream", "right": "downstream"}[n.Type]
				if rel == "" {
					rel = "peer"
				}
				out.Add(Finding{Type: KASN, Value: "AS" + strconv.Itoa(n.ASN), Source: "ripestat", Confidence: 80,
					Detail: rel + " of AS" + asn, Data: map[string]string{"relation": rel}})
			}
		}
		return nil
	},
}

// ---------------------------------------------------------------------------
// Vulnerabilities: CVE -> prioritised issue using CISA KEV and FIRST EPSS,
// instead of a flat "CVE wall".
// ---------------------------------------------------------------------------

var (
	kevOnce sync.Once
	kevSet  map[string]string // CVE -> vulnerability name
)

const kevURL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

func kevPath() string { return filepath.Join(dataDir(), "data", "kev.json") }

func parseKEV(b []byte) map[string]string {
	var k struct {
		Vulnerabilities []struct {
			CveID string `json:"cveID"`
			Name  string `json:"vulnerabilityName"`
		} `json:"vulnerabilities"`
	}
	m := map[string]string{}
	if json.Unmarshal(b, &k) == nil {
		for _, v := range k.Vulnerabilities {
			m[v.CveID] = v.Name
		}
	}
	return m
}

// loadKEV uses the offline pack; if missing or older than 3 days it is
// fetched once and stored.
func loadKEV(ctx context.Context) map[string]string {
	kevOnce.Do(func() {
		if st, err := os.Stat(kevPath()); err == nil && time.Since(st.ModTime()) < 3*day {
			b, _ := os.ReadFile(kevPath())
			kevSet = parseKEV(b)
			return
		}
		if code, b, err := fetch(ctx, kevURL, nil); err == nil && code == 200 {
			if m := parseKEV(b); len(m) > 0 {
				os.MkdirAll(filepath.Dir(kevPath()), 0o700)
				os.WriteFile(kevPath(), b, 0o600)
				kevSet = m
				return
			}
		}
		b, _ := os.ReadFile(kevPath()) // stale is better than nothing
		kevSet = parseKEV(b)
	})
	return kevSet
}

// vulnSeverity combines KEV membership and EPSS probability.
func vulnSeverity(inKEV bool, epss float64) Severity {
	switch {
	case inKEV:
		return SevCritical
	case epss >= 0.5:
		return SevHigh
	case epss >= 0.1:
		return SevMedium
	default:
		return SevLow
	}
}

var modVuln = &Module{
	Name: "vuln", Desc: "CVE prioritisation with CISA KEV + EPSS",
	In: []Kind{KCVE}, Out: []Kind{KIssue}, Timeout: 40 * time.Second, Retries: 1, Rate: 200 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		cve := strings.ToUpper(in.Value)
		kev := loadKEV(ctx)
		var ep struct {
			Data []struct {
				EPSS       string `json:"epss"`
				Percentile string `json:"percentile"`
			} `json:"data"`
		}
		epss := -1.0
		if getJSON(ctx, "https://api.first.org/data/v1/epss?cve="+cve, nil, day, &ep) == nil && len(ep.Data) > 0 {
			epss, _ = strconv.ParseFloat(ep.Data[0].EPSS, 64)
		}
		name, inKEV := kev[cve]
		sev := vulnSeverity(inKEV, epss)
		detail := in.Detail
		data := map[string]string{"check": "cve", "cve": cve, "ip": in.Data["ip"]}
		if inKEV {
			detail = "KNOWN EXPLOITED (CISA KEV): " + name + "; " + detail
			data["kev"] = "yes"
		}
		if epss >= 0 {
			detail = fmt.Sprintf("EPSS %.1f%%; %s", epss*100, detail)
			data["epss"] = strconv.FormatFloat(epss, 'f', 4, 64)
		}
		out.Add(Finding{Type: KIssue, Value: cve + " on " + in.Data["ip"], Severity: sev, Source: "kev+epss",
			Confidence: in.Confidence, Detail: detail, Data: data})
		return nil
	},
}

// ---------------------------------------------------------------------------
// TLS certificate: chain, expiry, SANs (new hostnames), weak protocol.
// ---------------------------------------------------------------------------

var tlsDial = func(ctx context.Context, host string, cfg *tls.Config) (*tls.ConnectionState, error) {
	d := &tls.Dialer{NetDialer: &net.Dialer{Timeout: 8 * time.Second}, Config: cfg}
	c, err := d.DialContext(ctx, "tcp", net.JoinHostPort(host, "443"))
	if err != nil {
		return nil, err
	}
	defer c.Close()
	st := c.(*tls.Conn).ConnectionState()
	return &st, nil
}

func certIssues(host string, cert *x509.Certificate, verifyErr error, now time.Time) []Finding {
	var fs []Finding
	left := cert.NotAfter.Sub(now)
	data := map[string]string{"check": "tls", "host": host, "not_after": cert.NotAfter.Format("2006-01-02")}
	switch {
	case left < 0:
		fs = append(fs, Finding{Type: KIssue, Value: "Expired certificate: " + host, Severity: SevHigh,
			Detail: "expired " + cert.NotAfter.Format("2006-01-02"), Data: data})
	case left < 14*day:
		fs = append(fs, Finding{Type: KIssue, Value: "Certificate expires soon: " + host, Severity: SevMedium,
			Detail: fmt.Sprintf("expires in %d days (%s)", int(left.Hours()/24), cert.NotAfter.Format("2006-01-02")), Data: data})
	}
	if verifyErr != nil && left >= 0 {
		fs = append(fs, Finding{Type: KIssue, Value: "Untrusted certificate: " + host, Severity: SevMedium,
			Detail: shorten(verifyErr.Error(), 90), Data: data})
	}
	return fs
}

var modCert = &Module{
	Name: "tls", Desc: "TLS certificate: expiry, trust, SAN hostnames, legacy TLS",
	In: []Kind{KDomain, KHost}, Out: []Kind{KCert, KHost, KIssue}, Timeout: 20 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if in.Data["rr"] == "MX" || in.Data["rr"] == "NS" {
			return nil
		}
		st, err := tlsDial(ctx, in.Value, &tls.Config{ServerName: in.Value, InsecureSkipVerify: true})
		if err != nil || len(st.PeerCertificates) == 0 {
			return fmt.Errorf("%w: no TLS", errPermanent)
		}
		leaf := st.PeerCertificates[0]
		inter := x509.NewCertPool()
		for _, c := range st.PeerCertificates[1:] {
			inter.AddCert(c)
		}
		_, verr := leaf.Verify(x509.VerifyOptions{DNSName: in.Value, Intermediates: inter})
		out.Add(Finding{Type: KCert, Value: leaf.Subject.CommonName + " #" + leaf.SerialNumber.Text(16), Source: "tls", Confidence: 100,
			Detail: "issuer " + leaf.Issuer.CommonName + ", valid until " + leaf.NotAfter.Format("2006-01-02"),
			Data:   map[string]string{"host": in.Value, "issuer": leaf.Issuer.CommonName, "not_after": leaf.NotAfter.Format(time.RFC3339)}})
		for _, f := range certIssues(in.Value, leaf, verr, time.Now()) {
			f.Source = "tls"
			out.Add(f)
		}
		for _, san := range leaf.DNSNames {
			out.Add(Finding{Type: KHost, Value: strings.ToLower(strings.TrimPrefix(san, "*.")), Source: "tls-san", Confidence: 90})
		}
		// Legacy protocol check (testssl-light): does the server still accept TLS 1.0/1.1?
		if _, err := tlsDial(ctx, in.Value, &tls.Config{ServerName: in.Value, InsecureSkipVerify: true,
			MinVersion: tls.VersionTLS10, MaxVersion: tls.VersionTLS11}); err == nil {
			out.Add(Finding{Type: KIssue, Value: "Legacy TLS 1.0/1.1 accepted: " + in.Value, Severity: SevLow, Source: "tls",
				Data: map[string]string{"check": "tls", "host": in.Value}})
		}
		return nil
	},
}

// ---------------------------------------------------------------------------
// Web exposure: files that must never be public.
// ---------------------------------------------------------------------------

type exposureProbe struct {
	path, must, name string
	sev              Severity
}

var exposureProbes = []exposureProbe{
	{"/.git/HEAD", "ref: refs/", "Exposed .git repository", SevCritical},
	{"/.env", "=", "Exposed .env file", SevCritical},
	{"/.svn/entries", "dir", "Exposed .svn metadata", SevHigh},
	{"/.DS_Store", "Bud1", "Exposed .DS_Store listing", SevLow},
	{"/server-status", "Apache Server Status", "Apache server-status public", SevMedium},
}

func exposureHit(p exposureProbe, code int, body []byte) bool {
	if code != 200 || len(body) == 0 {
		return false
	}
	b := string(body)
	if p.path == "/.env" { // HTML error pages often contain '='
		low := strings.ToLower(b)
		return !strings.Contains(low, "<html") && !strings.Contains(low, "<!doctype") && strings.Contains(b, "=")
	}
	return strings.Contains(b, p.must)
}

var modExposure = &Module{
	Name: "exposure", Desc: "Exposed .git/.env/.svn/server-status, security.txt",
	In: []Kind{KDomain, KHost}, Out: []Kind{KIssue, KURL}, Timeout: 30 * time.Second, Rate: 100 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if in.Data["rr"] == "MX" || in.Data["rr"] == "NS" {
			return nil
		}
		base := "https://" + in.Value
		if code, _, err := fetch(ctx, base+"/", nil); err != nil || code == 0 {
			return fmt.Errorf("%w: no web server", errPermanent)
		}
		for _, p := range exposureProbes {
			if code, body, err := fetch(ctx, base+p.path, nil); err == nil && exposureHit(p, code, body) {
				out.Add(Finding{Type: KIssue, Value: p.name + ": " + in.Value, Severity: p.sev, Source: "http", Confidence: 90,
					Detail: base + p.path, Data: map[string]string{"check": "exposure", "url": base + p.path}})
			}
		}
		if code, body, err := fetch(ctx, base+"/.well-known/security.txt", nil); err == nil && code == 200 && strings.Contains(strings.ToLower(string(body)), "contact:") {
			out.Add(Finding{Type: KURL, Value: base + "/.well-known/security.txt", Source: "http", Confidence: 100, Detail: "security.txt (disclosure contact)"})
		}
		return nil
	},
}
