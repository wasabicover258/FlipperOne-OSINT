package main

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

var domainRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z0-9-]{2,}$`)

func normalizeDomain(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	for _, p := range []string{"https://", "http://"} {
		s = strings.TrimPrefix(s, p)
	}
	if i := strings.IndexAny(s, "/?#"); i >= 0 {
		s = s[:i]
	}
	if i := strings.LastIndex(s, ":"); i >= 0 {
		s = s[:i]
	}
	s = strings.TrimPrefix(s, "www.")
	return strings.Trim(s, ".")
}

func runDomain(raw string) {
	d := normalizeDomain(raw)
	head("Domain recon: %s", d)
	if !domainRe.MatchString(d) {
		warn("Invalid domain (example: example.com)")
		return
	}

	dnsRecords(d)
	head("Email security")
	mailSecurity(d)
	head("Registration (RDAP)")
	rdapSummary(d)
	head("Web server")
	httpCheck(d)
	head("TLS certificate")
	tlsCheck(d)
	head("Web exposure")
	webExposure(d)

	// Subdomains feed the infrastructure tree, so collect them first.
	hostIPs := subdomains(d)
	infraTree(d, hostIPs)
}

func dnsRecords(d string) {
	head("DNS")
	r := net.DefaultResolver

	ctx, cancel := dnsCtx(6)
	addrs, err := r.LookupIPAddr(ctx, d)
	cancel()
	if err != nil || len(addrs) == 0 {
		warn("Domain does not resolve (%s)", shorten(fmt.Sprint(err), 50))
	}
	var v4 []string
	for _, a := range addrs {
		if a.IP.To4() != nil {
			v4 = append(v4, a.IP.String())
			found("A: %s", a.IP)
		} else {
			found("AAAA: %s", a.IP)
		}
	}
	for i, ip := range v4 {
		if i >= 3 {
			break
		}
		ctx, cancel := dnsCtx(5)
		names, err := r.LookupAddr(ctx, ip)
		cancel()
		if err == nil && len(names) > 0 {
			info("rDNS %s: %s", ip, strings.TrimSuffix(names[0], "."))
		}
	}

	ctx, cancel = dnsCtx(5)
	if cname, err := r.LookupCNAME(ctx, d); err == nil && strings.TrimSuffix(cname, ".") != d {
		found("CNAME: %s", strings.TrimSuffix(cname, "."))
	}
	cancel()

	ctx, cancel = dnsCtx(5)
	if nss, err := r.LookupNS(ctx, d); err == nil {
		for i, ns := range nss {
			if i >= 6 {
				break
			}
			found("NS: %s", strings.TrimSuffix(ns.Host, "."))
		}
	}
	cancel()

	// SOA, CAA and DNSSEC come from DNS over HTTPS (the system resolver cannot
	// return them).
	if soa := dohData(d, "SOA"); len(soa) > 0 {
		f := strings.Fields(soa[0])
		if len(f) >= 1 {
			info("SOA primary NS: %s", strings.TrimSuffix(f[0], "."))
		}
	}
	caa := dohData(d, "CAA")
	if len(caa) > 0 {
		var issuers []string
		for _, c := range caa {
			f := strings.Fields(c)
			if len(f) >= 3 && (f[1] == "issue" || f[1] == "issuewild") {
				issuers = append(issuers, strings.Trim(f[2], "\""))
			}
		}
		if len(issuers) > 0 {
			found("CAA: only %s may issue certificates", strings.Join(uniq(issuers), ", "))
		} else {
			info("CAA record present")
		}
	} else {
		miss("CAA: none (any CA may issue certificates)")
	}

	if rep, err := doh(d, "DNSKEY"); err == nil && rep != nil {
		if len(rep.Answer) > 0 {
			found("DNSSEC: signed (%d DNSKEY, validated=%v)", len(rep.Answer), rep.AD)
		} else {
			miss("DNSSEC: not signed")
		}
	}
	zoneTransfer(d)
}

// uniq removes duplicates, preserving order.
func uniq(in []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, s := range in {
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

// ---------------------------------------------------------------------------
// Email / domain security posture, with an overall grade.
// ---------------------------------------------------------------------------

var dkimSelectors = []string{
	"google", "default", "selector1", "selector2", "k1", "k2", "dkim",
	"mail", "s1", "s2", "mandrill", "mailjet", "sendgrid", "amazonses",
	"zoho", "protonmail", "protonmail2", "protonmail3", "fm1", "fm2", "fm3",
	"everlytickey1", "mxvault", "sig1", "scph0", "key1", "pic",
}

func mailSecurity(d string) {
	r := net.DefaultResolver
	score, max := 0, 0

	// SPF
	ctx, cancel := dnsCtx(6)
	txts, _ := r.LookupTXT(ctx, d)
	cancel()
	spf := ""
	for _, t := range txts {
		if strings.HasPrefix(strings.ToLower(t), "v=spf1") {
			spf = t
		}
	}
	max += 2
	if spf != "" {
		policy := "neutral"
		switch {
		case strings.Contains(spf, "-all"):
			policy = "strict (-all)"
			score += 2
		case strings.Contains(spf, "~all"):
			policy = "softfail (~all)"
			score += 1
		case strings.Contains(spf, "?all"):
			policy = "neutral (?all)"
		case strings.Contains(spf, "+all"):
			policy = "open (+all) - weak"
		}
		found("SPF: present, %s", policy)
		if n := spfLookups(spf, d, 0, map[string]bool{}); n > 10 {
			warn("SPF exceeds 10 DNS lookups (%d) - may fail validation", n)
		}
	} else {
		miss("SPF: no record")
	}

	// DMARC
	ctx, cancel = dnsCtx(6)
	dtxt, _ := r.LookupTXT(ctx, "_dmarc."+d)
	cancel()
	dmarc := ""
	for _, t := range dtxt {
		if strings.HasPrefix(strings.ToUpper(t), "V=DMARC1") {
			dmarc = t
		}
	}
	max += 3
	if dmarc != "" {
		p := dmarcTag(dmarc, "p")
		switch p {
		case "reject":
			score += 3
			found("DMARC: p=reject (strongest)")
		case "quarantine":
			score += 2
			found("DMARC: p=quarantine")
		case "none":
			score += 1
			warn("DMARC: p=none (monitoring only)")
		default:
			found("DMARC: present")
		}
		if rua := dmarcTag(dmarc, "rua"); rua != "" {
			info("DMARC reports to: %s", shorten(rua, 60))
		}
	} else {
		miss("DMARC: no record")
	}

	// DKIM selector probe
	max += 1
	found2 := dkimProbe(d)
	if len(found2) > 0 {
		score += 1
		found("DKIM: selectors found: %s", strings.Join(found2, ", "))
	} else {
		miss("DKIM: no common selector found (may use a custom one)")
	}

	// MTA-STS
	max += 1
	ctx, cancel = dnsCtx(5)
	mta, _ := r.LookupTXT(ctx, "_mta-sts."+d)
	cancel()
	hasMTA := false
	for _, t := range mta {
		if strings.HasPrefix(strings.ToLower(t), "v=stsv1") {
			hasMTA = true
		}
	}
	if hasMTA {
		score += 1
		found("MTA-STS: enabled (enforced TLS for inbound mail)")
	} else {
		miss("MTA-STS: not configured")
	}

	// TLS-RPT and BIMI are informational extras.
	ctx, cancel = dnsCtx(5)
	tlsrpt, _ := r.LookupTXT(ctx, "_smtp._tls."+d)
	cancel()
	for _, t := range tlsrpt {
		if strings.HasPrefix(strings.ToLower(t), "v=tlsrptv1") {
			info("TLS-RPT: present")
		}
	}
	ctx, cancel = dnsCtx(5)
	bimi, _ := r.LookupTXT(ctx, "default._bimi."+d)
	cancel()
	for _, t := range bimi {
		if strings.HasPrefix(strings.ToLower(t), "v=bimi1") {
			info("BIMI: present (brand logo)")
		}
	}

	info("Mail security grade: %s (%d/%d)", grade(score, max), score, max)
}

// spfLookups counts the DNS-lookup mechanisms in an SPF record, following
// include/redirect once per domain (RFC 7208 caps this at 10).
func spfLookups(spf, d string, depth int, seen map[string]bool) int {
	if depth > 5 || seen[d] {
		return 0
	}
	seen[d] = true
	n := 0
	for _, tok := range strings.Fields(spf) {
		tok = strings.ToLower(tok)
		switch {
		case strings.HasPrefix(tok, "include:"), strings.HasPrefix(tok, "redirect="):
			n++
			sub := tok[strings.IndexAny(tok, ":=")+1:]
			ctx, cancel := dnsCtx(4)
			t, _ := net.DefaultResolver.LookupTXT(ctx, sub)
			cancel()
			for _, r := range t {
				if strings.HasPrefix(strings.ToLower(r), "v=spf1") {
					n += spfLookups(r, sub, depth+1, seen)
				}
			}
		case tok == "a", tok == "mx", strings.HasPrefix(tok, "a:"),
			strings.HasPrefix(tok, "mx:"), strings.HasPrefix(tok, "ptr"),
			strings.HasPrefix(tok, "exists:"):
			n++
		}
	}
	return n
}

func dkimProbe(d string) []string {
	var mu sync.Mutex
	var found []string
	sem := make(chan struct{}, 10)
	var wg sync.WaitGroup
	for _, sel := range dkimSelectors {
		wg.Add(1)
		go func(sel string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			ctx, cancel := dnsCtx(4)
			t, err := net.DefaultResolver.LookupTXT(ctx, sel+"._domainkey."+d)
			cancel()
			if err == nil {
				for _, rec := range t {
					if strings.Contains(strings.ToLower(rec), "k=") || strings.Contains(strings.ToLower(rec), "p=") || strings.Contains(strings.ToLower(rec), "dkim1") {
						mu.Lock()
						found = append(found, sel)
						mu.Unlock()
						break
					}
				}
			}
		}(sel)
	}
	wg.Wait()
	sort.Strings(found)
	return found
}

func dmarcTag(rec, tag string) string {
	for _, part := range strings.Split(rec, ";") {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(strings.ToLower(part), tag+"=") {
			return strings.TrimSpace(part[len(tag)+1:])
		}
	}
	return ""
}

func grade(score, max int) string {
	if max == 0 {
		return "n/a"
	}
	pct := score * 100 / max
	switch {
	case pct >= 90:
		return "A"
	case pct >= 75:
		return "B"
	case pct >= 55:
		return "C"
	case pct >= 35:
		return "D"
	case pct >= 15:
		return "E"
	default:
		return "F"
	}
}

// rdapSummary shows registrar and dates. Personal data is not printed.
func rdapSummary(d string) {
	resp, body, err := get(client, "https://rdap.org/domain/"+d)
	if err != nil {
		warn("RDAP not reachable")
		return
	}
	if resp.StatusCode == 404 {
		miss("No RDAP record (TLD without RDAP, or domain free)")
		return
	}
	if resp.StatusCode != 200 {
		warn("RDAP: HTTP %d", resp.StatusCode)
		return
	}
	var rd struct {
		Status []string `json:"status"`
		Events []struct {
			Action string `json:"eventAction"`
			Date   string `json:"eventDate"`
		} `json:"events"`
		Entities []struct {
			Roles      []string `json:"roles"`
			VcardArray []any    `json:"vcardArray"`
		} `json:"entities"`
		Nameservers []struct {
			Name string `json:"ldhName"`
		} `json:"nameservers"`
	}
	if err := json.Unmarshal(body, &rd); err != nil {
		warn("RDAP response not readable")
		return
	}
	for _, e := range rd.Entities {
		isReg := false
		for _, role := range e.Roles {
			if role == "registrar" {
				isReg = true
			}
		}
		if !isReg || len(e.VcardArray) < 2 {
			continue
		}
		props, _ := e.VcardArray[1].([]any)
		for _, p := range props {
			arr, _ := p.([]any)
			if len(arr) >= 4 && arr[0] == "fn" {
				if name, ok := arr[3].(string); ok {
					found("Registrar: %s", name)
				}
			}
		}
	}
	labels := map[string]string{"registration": "Registered", "expiration": "Expires", "last changed": "Changed"}
	for _, ev := range rd.Events {
		if l, ok := labels[ev.Action]; ok && len(ev.Date) >= 10 {
			found("%s: %s", l, ev.Date[:10])
		}
	}
	if len(rd.Status) > 0 {
		info("Status: %s", shorten(strings.Join(rd.Status, ", "), 90))
	}
}

var (
	titleRe = regexp.MustCompile(`(?is)<title[^>]*>(.*?)</title>`)
	genRe   = regexp.MustCompile(`(?is)<meta[^>]+name=["']generator["'][^>]+content=["']([^"']+)`)
)

// techFingerprint guesses the stack from headers, cookies and HTML markers.
func techFingerprint(resp *http.Response, body []byte) []string {
	var tech []string
	add := func(s string) { tech = append(tech, s) }
	h := resp.Header
	hl := func(k string) string { return strings.ToLower(h.Get(k)) }
	server := hl("Server")
	switch {
	case strings.Contains(server, "nginx"):
		add("nginx")
	case strings.Contains(server, "apache"):
		add("Apache")
	case strings.Contains(server, "iis"):
		add("Microsoft IIS")
	case strings.Contains(server, "litespeed"):
		add("LiteSpeed")
	case strings.Contains(server, "caddy"):
		add("Caddy")
	case strings.Contains(server, "cloudflare"):
		add("Cloudflare")
	}
	if hl("x-powered-by") != "" {
		add(h.Get("X-Powered-By"))
	}
	bl := strings.ToLower(string(body))
	markers := []struct{ needle, name string }{
		{"wp-content", "WordPress"}, {"/wp-json", "WordPress"},
		{"drupal-settings-json", "Drupal"}, {"joomla", "Joomla"},
		{"typo3", "TYPO3"}, {"shopify", "Shopify"}, {"magento", "Magento"},
		{"woocommerce", "WooCommerce"}, {"wixstatic", "Wix"},
		{"squarespace", "Squarespace"}, {"__next", "Next.js"},
		{"_nuxt", "Nuxt"}, {"react", "React"}, {"ng-version", "Angular"},
		{"vue", "Vue"}, {"gatsby", "Gatsby"}, {"laravel_session", "Laravel"},
		{"csrftoken", "Django"}, {"phpsessid", "PHP"}, {"jsessionid", "Java"},
		{"hubspot", "HubSpot"}, {"cloudfront", "AWS CloudFront"},
	}
	for _, m := range markers {
		if strings.Contains(bl, m.needle) || strings.Contains(strings.ToLower(h.Get("Set-Cookie")), m.needle) {
			add(m.name)
		}
	}
	// CDN / WAF hints from headers
	for k, label := range map[string]string{
		"cf-ray": "Cloudflare", "x-amz-cf-id": "AWS CloudFront",
		"x-fastly-request-id": "Fastly", "x-akamai-transformed": "Akamai",
		"x-vercel-id": "Vercel", "x-nf-request-id": "Netlify",
		"x-sucuri-id": "Sucuri WAF", "x-served-by": "Varnish/Fastly",
	} {
		if h.Get(k) != "" {
			add(label)
		}
	}
	return uniq(tech)
}

func httpCheck(d string) {
	var resp *http.Response
	var body []byte
	var err error
	base := "https://" + d
	resp, body, err = get(client, base+"/")
	if err != nil {
		warn("HTTPS not reachable: %s", shorten(err.Error(), 50))
		base = "http://" + d
		resp, body, err = get(client, base+"/")
		if err != nil {
			warn("HTTP not reachable")
			return
		}
	}
	found("Status: %d  %s", resp.StatusCode, shorten(resp.Request.URL.String(), 55))
	if s := resp.Header.Get("Server"); s != "" {
		info("Server: %s", shorten(s, 60))
	}
	if m := titleRe.FindSubmatch(body); m != nil {
		info("Title: %s", shorten(string(m[1]), 70))
	}
	if m := genRe.FindSubmatch(body); m != nil {
		info("Generator: %s", shorten(string(m[1]), 60))
	}
	if tech := techFingerprint(resp, body); len(tech) > 0 {
		found("Tech: %s", shorten(strings.Join(tech, ", "), 90))
	}

	checks := []struct{ h, label string }{
		{"Strict-Transport-Security", "HSTS"},
		{"Content-Security-Policy", "CSP"},
		{"X-Frame-Options", "X-Frame-Options"},
		{"X-Content-Type-Options", "X-Content-Type"},
		{"Referrer-Policy", "Referrer-Policy"},
		{"Permissions-Policy", "Permissions-Policy"},
	}
	var have, lack []string
	for _, c := range checks {
		if resp.Header.Get(c.h) != "" {
			have = append(have, c.label)
		} else {
			lack = append(lack, c.label)
		}
	}
	if len(have) > 0 {
		found("Security headers: %s", strings.Join(have, ", "))
	}
	if len(lack) > 0 {
		miss("Headers missing: %s", strings.Join(lack, ", "))
	}
	info("Header grade: %s (%d/%d)", grade(len(have), len(checks)), len(have), len(checks))

	for _, p := range []string{"/robots.txt", "/.well-known/security.txt"} {
		r2, b2, err := get(client, base+p)
		if err != nil {
			continue
		}
		t := strings.TrimSpace(string(b2))
		if r2.StatusCode == 200 && t != "" && !strings.HasPrefix(strings.ToLower(t), "<") {
			found("%s present", p)
		} else {
			miss("%s missing", p)
		}
	}
}

func tlsCheck(d string) {
	dialer := &net.Dialer{Timeout: 8 * time.Second}
	verified := true
	conn, err := tls.DialWithDialer(dialer, "tcp", d+":443", &tls.Config{ServerName: d})
	if err != nil {
		verified = false
		conn, err = tls.DialWithDialer(dialer, "tcp", d+":443", &tls.Config{ServerName: d, InsecureSkipVerify: true})
		if err != nil {
			warn("No TLS on port 443")
			return
		}
	}
	defer conn.Close()
	st := conn.ConnectionState()
	vers := map[uint16]string{tls.VersionTLS10: "TLS 1.0", tls.VersionTLS11: "TLS 1.1", tls.VersionTLS12: "TLS 1.2", tls.VersionTLS13: "TLS 1.3"}
	if verified {
		found("Certificate valid and trusted")
	} else {
		warn("Certificate not trusted")
	}
	if st.Version <= tls.VersionTLS11 {
		warn("Protocol: %s (outdated)", vers[st.Version])
	} else {
		info("Protocol: %s  %s", vers[st.Version], tls.CipherSuiteName(st.CipherSuite))
	}
	if len(st.PeerCertificates) == 0 {
		return
	}
	c := st.PeerCertificates[0]
	info("Issuer: %s", shorten(c.Issuer.CommonName+" "+strings.Join(c.Issuer.Organization, " "), 70))
	info("Valid: %s to %s", c.NotBefore.Format("2006-01-02"), c.NotAfter.Format("2006-01-02"))
	left := int(time.Until(c.NotAfter).Hours() / 24)
	if left < 0 {
		warn("Certificate expired (%d days ago)", -left)
	} else if left < 21 {
		warn("Expires in %d days", left)
	} else {
		found("Still valid for %d days", left)
	}
	names := c.DNSNames
	if len(names) > 0 {
		shownNames := names
		if len(shownNames) > 8 {
			shownNames = shownNames[:8]
		}
		info("Cert names: %s", strings.Join(shownNames, ", "))
	}
}

// subdomains discovers names from certificate logs and a DNS sweep, prints
// the live ones and returns a hostname -> IPs map for the infrastructure tree.
func subdomains(d string) map[string][]string {
	head("Subdomains")
	cand := map[string]bool{d: true}

	// 1) Certificate transparency logs (crt.sh).
	crt := &http.Client{Timeout: 25 * time.Second}
	resp, body, err := get(crt, "https://crt.sh/?q=%25."+d+"&output=json")
	if err != nil || resp.StatusCode != 200 {
		warn("crt.sh not reachable (using DNS sweep only)")
	} else {
		var rows []struct {
			Name string `json:"name_value"`
		}
		if json.Unmarshal(body, &rows) == nil {
			for _, r := range rows {
				for _, n := range strings.Split(r.Name, "\n") {
					n = strings.ToLower(strings.TrimPrefix(strings.TrimSpace(n), "*."))
					if n == d || strings.HasSuffix(n, "."+d) {
						cand[n] = true
					}
				}
			}
		} else {
			warn("crt.sh response not readable (maybe too large)")
		}
	}
	// 2) certspotter: a second certificate-transparency source.
	for _, n := range certspotterSubs(d) {
		n = strings.ToLower(strings.TrimPrefix(strings.TrimSpace(n), "*."))
		if n == d || strings.HasSuffix(n, "."+d) {
			cand[n] = true
		}
	}
	ctLen := len(cand)

	// 3) HackerTarget hostsearch: passive DNS that returns the IP directly.
	htHosts := hackertargetSubs(d)

	// 4) DNS sweep of common labels, to catch hosts not in any log.
	for _, s := range commonSubs {
		cand[s+"."+d] = true
	}
	for h := range htHosts {
		cand[h] = true
	}

	names := make([]string, 0, len(cand))
	for n := range cand {
		names = append(names, n)
	}
	sort.Strings(names)

	// Resolve all candidates, capped for time.
	limit := 220
	if len(names) > limit {
		names = names[:limit]
	}
	type res struct {
		name string
		ips  []string
	}
	out := make([]res, len(names))
	sem := make(chan struct{}, 30)
	var wg sync.WaitGroup
	for i := range names {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			out[i] = res{names[i], ipsOf(names[i])}
		}(i)
	}
	wg.Wait()

	hostIPs := map[string][]string{}
	for _, r := range out {
		if len(r.ips) > 0 {
			hostIPs[r.name] = r.ips
		}
	}
	// Add HackerTarget hosts (their IPs are authoritative even if our live
	// resolver did not answer for that name).
	for h, ips := range htHosts {
		if _, ok := hostIPs[h]; !ok {
			hostIPs[h] = ips
		}
	}
	live := 0
	var liveNames []string
	for n := range hostIPs {
		live++
		if n != d {
			liveNames = append(liveNames, n)
		}
	}
	info("Sources: crt.sh + certspotter logs, HackerTarget, DNS sweep")
	info("%d names from CT logs, %d common labels swept", ctLen-1, len(commonSubs))
	info("%d hosts resolve", live)
	sort.Strings(liveNames)
	shown := 0
	for _, n := range liveNames {
		if shown >= 50 {
			info("... and %d more", len(liveNames)-shown)
			break
		}
		found("%s  %s", n, hostIPs[n][0])
		shown++
	}
	if live <= 1 {
		miss("No subdomains found")
	}
	return hostIPs
}

// infraTree groups every discovered host by IP, enriches the busiest addresses
// and prints them as a tree: IP -> operator, open ports, known CVEs, hosts.
func infraTree(d string, hostIPs map[string][]string) {
	head("Infrastructure map")
	// Group hosts by IPv4 address.
	ipHosts := map[string][]string{}
	for host, ips := range hostIPs {
		for _, ip := range ips {
			if net.ParseIP(ip).To4() != nil {
				ipHosts[ip] = append(ipHosts[ip], host)
			}
		}
	}
	if len(ipHosts) == 0 {
		miss("No IPv4 hosts to map")
		return
	}
	ips := make([]string, 0, len(ipHosts))
	for ip := range ipHosts {
		ips = append(ips, ip)
		sort.Strings(ipHosts[ip])
	}
	// Busiest IPs first, capped so the run stays within the time budget.
	sort.Slice(ips, func(i, j int) bool {
		if len(ipHosts[ips[i]]) != len(ipHosts[ips[j]]) {
			return len(ipHosts[ips[i]]) > len(ipHosts[ips[j]])
		}
		return ips[i] < ips[j]
	})
	info("%d unique IPv4 addresses behind %s", len(ips), d)
	topN := 14
	if len(ips) < topN {
		topN = len(ips)
	}

	data := make([]*ipData, topN)
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup
	for i := 0; i < topN; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			data[i] = enrichIP(ips[i])
		}(i)
	}
	wg.Wait()

	// Live port scan of the mapped IPs (connect scan, focused port list).
	liveOpen := make([][]int, topN)
	banners := make([]string, topN)
	var swg sync.WaitGroup
	ssem := make(chan struct{}, 6)
	for i := 0; i < topN; i++ {
		swg.Add(1)
		go func(i int) {
			defer swg.Done()
			ssem <- struct{}{}
			defer func() { <-ssem }()
			op := portScan(ips[i], topPortsLite, 1200*time.Millisecond, 48)
			liveOpen[i] = op
			if len(op) > 0 {
				banners[i] = bannerFor(ips[i], op)
			}
		}(i)
	}
	swg.Wait()

	totalVulns := 0
	for i := 0; i < topN; i++ {
		ip := ips[i]
		dd := data[i]
		loc := strings.TrimSpace(dd.asn + " " + dd.org)
		if dd.country != "" {
			loc = strings.TrimSpace(loc + ", " + dd.country)
		}
		if loc == "" {
			loc = "operator unknown"
		}
		found("%s  (%s)", ip, shorten(loc, 58))
		// hosts on this IP
		hs := ipHosts[ip]
		if len(hs) > 4 {
			info("   hosts: %s +%d more", strings.Join(hs[:4], ", "), len(hs)-4)
		} else {
			info("   hosts: %s", strings.Join(hs, ", "))
		}
		if len(liveOpen[i]) > 0 {
			info("   open now: %s", shorten(portsStr(liveOpen[i]), 76))
		} else if len(dd.ports) > 0 {
			info("   ports (Shodan): %s", shorten(portsStr(dd.ports), 72))
		}
		if banners[i] != "" {
			info("   service: %s", banners[i])
		}
		if len(dd.vulns) > 0 {
			totalVulns += len(dd.vulns)
			v := dd.vulns
			if len(v) > 6 {
				v = v[:6]
			}
			warn("   CVEs (%d): %s", len(dd.vulns), strings.Join(v, ", "))
		}
	}
	if len(ips) > topN {
		info("%d more addresses not expanded", len(ips)-topN)
	}
	if totalVulns > 0 {
		warn("Attack surface: %d known CVEs across the mapped hosts", totalVulns)
	} else {
		info("No known CVEs on the mapped hosts (Shodan InternetDB)")
	}
}
