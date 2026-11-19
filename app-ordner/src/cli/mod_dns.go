package main

import (
	"context"
	"net"
	"net/url"
	"strings"
	"sync"
	"time"
)

// allModules is the module registry. Order only matters for display.
func allModules() []*Module {
	return []*Module{
		modDNS, modWildcard, modPermute,
		modCrtsh, modCertspotter, modWayback, modOTX, modURLScan, modHackerTarget,
		modVTSubs, modSecurityTrails,
		modCert, modTakeover, modExposure, modLookalike,
		modInternetDB, modShodanHost, modRIPE, modASNPrefixes, modVuln,
	}
}

// hostOK filters junk out of subdomain sources.
func hostOK(h, domain string) (string, bool) {
	h = strings.ToLower(strings.TrimSpace(strings.TrimSuffix(h, ".")))
	h = strings.TrimPrefix(h, "*.")
	if h == "" || strings.ContainsAny(h, " */@:_") || len(h) > 253 {
		return "", false
	}
	if h != domain && !strings.HasSuffix(h, "."+domain) {
		return "", false
	}
	return h, true
}

// addHosts emits every valid in-domain host once.
func addHosts(out *Out, domain, source string, hosts []string) {
	seen := map[string]bool{}
	for _, h := range hosts {
		if h, ok := hostOK(h, domain); ok && !seen[h] && h != domain {
			seen[h] = true
			out.Add(Finding{Type: KHost, Value: h, Source: source, Confidence: 70})
		}
	}
}

// ---------------------------------------------------------------------------

var modDNS = &Module{
	Name: "dns", Desc: "A/AAAA/MX/NS/CNAME via DNS-over-HTTPS",
	In: []Kind{KDomain, KHost}, Out: []Kind{KIP, KHost, KDomain},
	Timeout: 15 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		name := in.Value
		if in.Type == KHost {
			if d := registrableDomain(name); d != "" && d != name {
				out.Add(Finding{Type: KDomain, Value: d, Source: "derived", Confidence: 100})
			}
		}
		var wg sync.WaitGroup
		var mu sync.Mutex
		res := map[string][]string{}
		for _, t := range []string{"A", "AAAA", "CNAME", "MX", "NS"} {
			if in.Type == KHost && (t == "MX" || t == "NS") {
				continue
			}
			wg.Add(1)
			go func(t string) {
				defer wg.Done()
				v := dohValues(ctx, name, t)
				mu.Lock()
				res[t] = v
				mu.Unlock()
			}(t)
		}
		wg.Wait()
		if ctx.Err() != nil {
			return ctx.Err()
		}
		for _, t := range []string{"A", "AAAA"} {
			for _, ip := range res[t] {
				if net.ParseIP(ip) != nil {
					out.Add(Finding{Type: KIP, Value: ip, Source: "dns", Confidence: 100, Detail: name + " " + t})
				}
			}
		}
		for _, c := range res["CNAME"] {
			out.Add(Finding{Type: KHost, Value: strings.ToLower(c), Source: "dns", Confidence: 100, Detail: "CNAME of " + name, Data: map[string]string{"rr": "CNAME"}})
		}
		for _, mx := range res["MX"] {
			if f := strings.Fields(mx); len(f) == 2 {
				out.Add(Finding{Type: KHost, Value: strings.ToLower(strings.TrimSuffix(f[1], ".")), Source: "dns", Confidence: 100, Detail: "MX of " + name, Data: map[string]string{"rr": "MX"}})
			}
		}
		for _, ns := range res["NS"] {
			out.Add(Finding{Type: KHost, Value: strings.ToLower(ns), Source: "dns", Confidence: 100, Detail: "NS of " + name, Data: map[string]string{"rr": "NS"}})
		}
		return nil
	},
}

// wildcardIPs answers whether *.domain resolves (random label test).
func wildcardIPs(ctx context.Context, domain string) []string {
	return dohValues(ctx, "zq"+controlName("")[2:12]+"."+domain, "A")
}

var modWildcard = &Module{
	Name: "wildcard", Desc: "Wildcard DNS detection",
	In: []Kind{KDomain}, Out: []Kind{KIssue},
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if ips := wildcardIPs(ctx, in.Value); len(ips) > 0 {
			out.Add(Finding{Type: KIssue, Value: "Wildcard DNS: *." + in.Value, Severity: SevInfo,
				Detail: "every name resolves to " + strings.Join(ips, ", ") + "; brute-forced names are unreliable",
				Data:   map[string]string{"check": "wildcard"}})
		}
		return nil
	},
}

// Common environment and service prefixes (dnsrecon/amass style word list,
// kept short for the handheld).
var permutePrefixes = []string{
	"www", "mail", "webmail", "smtp", "imap", "mx", "vpn", "remote", "portal", "admin",
	"api", "api-dev", "api-staging", "app", "dev", "dev-api", "development", "staging", "stage",
	"test", "testing", "qa", "uat", "preprod", "sandbox", "demo", "beta", "old", "legacy",
	"git", "gitlab", "jenkins", "ci", "jira", "confluence", "wiki", "docs", "status",
	"grafana", "kibana", "monitor", "intranet", "sso", "auth", "login", "cdn", "static",
	"assets", "files", "backup", "db", "shop", "store", "blog", "m", "autodiscover",
}

var modPermute = &Module{
	Name: "permute", Desc: "Prefix permutations (dev-, staging- ...), skipped on wildcard DNS",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 60 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if len(wildcardIPs(ctx, in.Value)) > 0 {
			return nil
		}
		sem := make(chan struct{}, 10)
		var wg sync.WaitGroup
		for _, p := range permutePrefixes {
			wg.Add(1)
			go func(h string) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				if len(dohValues(ctx, h, "A")) > 0 || len(dohValues(ctx, h, "AAAA")) > 0 {
					out.Add(Finding{Type: KHost, Value: h, Source: "permutation", Confidence: 95})
				}
			}(p + "." + in.Value)
		}
		wg.Wait()
		return ctx.Err()
	},
}

// ---------------------------------------------------------------------------
// Passive subdomain sources
// ---------------------------------------------------------------------------

const day = 24 * time.Hour

var modCrtsh = &Module{
	Name: "crtsh", Desc: "Certificate Transparency (crt.sh)",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 45 * time.Second, Retries: 2, Rate: 2 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var rows []struct {
			NameValue string `json:"name_value"`
		}
		if err := getJSON(ctx, "https://crt.sh/?q=%25."+url.QueryEscape(in.Value)+"&output=json", nil, day, &rows); err != nil {
			return err
		}
		var hs []string
		for _, r := range rows {
			hs = append(hs, strings.Split(r.NameValue, "\n")...)
		}
		addHosts(out, in.Value, "crt.sh", hs)
		return nil
	},
}

var modCertspotter = &Module{
	Name: "certspotter", Desc: "Certificate Transparency (SSLMate Cert Spotter)",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var rows []struct {
			DNSNames []string `json:"dns_names"`
		}
		if err := getJSON(ctx, "https://api.certspotter.com/v1/issuances?domain="+in.Value+"&include_subdomains=true&expand=dns_names", nil, day, &rows); err != nil {
			return err
		}
		var hs []string
		for _, r := range rows {
			hs = append(hs, r.DNSNames...)
		}
		addHosts(out, in.Value, "certspotter", hs)
		return nil
	},
}

var modWayback = &Module{
	Name: "wayback", Desc: "Wayback Machine CDX: historic hostnames",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 45 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var rows [][]string
		u := "https://web.archive.org/cdx/search/cdx?url=*." + in.Value + "&output=json&fl=original&collapse=urlkey&limit=5000"
		if err := getJSON(ctx, u, nil, day, &rows); err != nil {
			return err
		}
		var hs []string
		for i, r := range rows {
			if i == 0 || len(r) == 0 { // header row
				continue
			}
			if p, err := url.Parse(r[0]); err == nil {
				hs = append(hs, p.Hostname())
			}
		}
		addHosts(out, in.Value, "wayback", hs)
		return nil
	},
}

var modOTX = &Module{
	Name: "otx", Desc: "AlienVault OTX passive DNS",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			PassiveDNS []struct {
				Hostname string `json:"hostname"`
			} `json:"passive_dns"`
		}
		if err := getJSON(ctx, "https://otx.alienvault.com/api/v1/indicators/domain/"+in.Value+"/passive_dns", nil, day, &r); err != nil {
			return err
		}
		var hs []string
		for _, p := range r.PassiveDNS {
			hs = append(hs, p.Hostname)
		}
		addHosts(out, in.Value, "otx", hs)
		return nil
	},
}

var modURLScan = &Module{
	Name: "urlscan", Desc: "urlscan.io public scans",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			Results []struct {
				Page struct {
					Domain string `json:"domain"`
				} `json:"page"`
			} `json:"results"`
		}
		if err := getJSON(ctx, "https://urlscan.io/api/v1/search/?q=domain:"+in.Value+"&size=200", nil, day, &r); err != nil {
			return err
		}
		var hs []string
		for _, x := range r.Results {
			hs = append(hs, x.Page.Domain)
		}
		addHosts(out, in.Value, "urlscan", hs)
		return nil
	},
}

var modHackerTarget = &Module{
	Name: "hackertarget", Desc: "HackerTarget host search",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		code, body, err := cachedFetch(ctx, "https://api.hackertarget.com/hostsearch/?q="+in.Value, nil, day)
		if err != nil {
			return err
		}
		if err := httpErr(code); err != nil {
			return err
		}
		var hs []string
		for _, l := range strings.Split(string(body), "\n") {
			if h, _, ok := strings.Cut(l, ","); ok {
				hs = append(hs, h)
			}
		}
		addHosts(out, in.Value, "hackertarget", hs)
		return nil
	},
}

var modVTSubs = &Module{
	Name: "virustotal", Desc: "VirusTotal subdomains", Key: "VIRUSTOTAL_API_KEY",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second, Rate: 15 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			Data []struct {
				ID string `json:"id"`
			} `json:"data"`
		}
		hdr := map[string]string{"x-apikey": out.eng.Keys["VIRUSTOTAL_API_KEY"]}
		if err := getJSON(ctx, "https://www.virustotal.com/api/v3/domains/"+in.Value+"/subdomains?limit=40", hdr, day, &r); err != nil {
			return err
		}
		var hs []string
		for _, d := range r.Data {
			hs = append(hs, d.ID)
		}
		addHosts(out, in.Value, "virustotal", hs)
		return nil
	},
}

var modSecurityTrails = &Module{
	Name: "securitytrails", Desc: "SecurityTrails subdomains", Key: "SECURITYTRAILS_API_KEY",
	In: []Kind{KDomain}, Out: []Kind{KHost}, Timeout: 30 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		var r struct {
			Subdomains []string `json:"subdomains"`
		}
		hdr := map[string]string{"APIKEY": out.eng.Keys["SECURITYTRAILS_API_KEY"]}
		if err := getJSON(ctx, "https://api.securitytrails.com/v1/domain/"+in.Value+"/subdomains", hdr, day, &r); err != nil {
			return err
		}
		var hs []string
		for _, s := range r.Subdomains {
			hs = append(hs, s+"."+in.Value)
		}
		addHosts(out, in.Value, "securitytrails", hs)
		return nil
	},
}
