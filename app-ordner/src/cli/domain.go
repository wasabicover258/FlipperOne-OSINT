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
	head("DOMAIN-CHECK: %s", d)
	if !domainRe.MatchString(d) {
		warn("UNGUELTIGE DOMAIN (BEISPIEL: BEISPIEL.DE)")
		return
	}
	dnsRecords(d)
	head("REGISTRIERUNG (RDAP)")
	rdapSummary(d)
	head("WEBSERVER")
	httpCheck(d)
	head("TLS-ZERTIFIKAT")
	tlsCheck(d)
	head("SUBDOMAINS (ZERTIFIKATS-LOGS)")
	subdomains(d)
}

func dnsRecords(d string) {
	head("DNS")
	r := net.DefaultResolver

	ctx, cancel := dnsCtx(6)
	addrs, err := r.LookupIPAddr(ctx, d)
	cancel()
	if err != nil || len(addrs) == 0 {
		warn("DOMAIN LOEST NICHT AUF (%s)", shorten(fmt.Sprint(err), 50))
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
			info("RDNS %s: %s", ip, strings.TrimSuffix(names[0], "."))
		}
	}

	ctx, cancel = dnsCtx(5)
	if cname, err := r.LookupCNAME(ctx, d); err == nil && strings.TrimSuffix(cname, ".") != d {
		found("CNAME: %s", strings.TrimSuffix(cname, "."))
	}
	cancel()

	ctx, cancel = dnsCtx(5)
	if mxs, err := r.LookupMX(ctx, d); err == nil {
		for i, mx := range mxs {
			if i >= 5 {
				break
			}
			found("MX %d: %s", mx.Pref, strings.TrimSuffix(mx.Host, "."))
		}
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

	ctx, cancel = dnsCtx(5)
	txts, _ := r.LookupTXT(ctx, d)
	cancel()
	spf := false
	shown := 0
	for _, t := range txts {
		if strings.HasPrefix(strings.ToLower(t), "v=spf1") {
			spf = true
		}
		if shown < 6 {
			found("TXT: %s", shorten(t, 100))
			shown++
		}
	}
	if spf {
		info("SPF VORHANDEN")
	} else {
		miss("SPF FEHLT")
	}
	ctx, cancel = dnsCtx(5)
	dm, _ := r.LookupTXT(ctx, "_dmarc."+d)
	cancel()
	hasDmarc := false
	for _, t := range dm {
		if strings.HasPrefix(strings.ToUpper(t), "V=DMARC1") {
			hasDmarc = true
			info("DMARC: %s", shorten(t, 90))
		}
	}
	if !hasDmarc {
		miss("DMARC FEHLT")
	}
}

// rdapSummary zeigt Registrar und Fristen. Personenbezogene Daten werden nicht ausgegeben.
func rdapSummary(d string) {
	resp, body, err := get(client, "https://rdap.org/domain/"+d)
	if err != nil {
		warn("RDAP NICHT ERREICHBAR")
		return
	}
	if resp.StatusCode == 404 {
		miss("KEIN RDAP-EINTRAG (TLD UNTERSTUETZT RDAP NICHT ODER FREI)")
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
		warn("RDAP-ANTWORT NICHT LESBAR")
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
					found("REGISTRAR: %s", name)
				}
			}
		}
	}
	labels := map[string]string{"registration": "REGISTRIERT", "expiration": "LAEUFT AB", "last changed": "GEAENDERT"}
	for _, ev := range rd.Events {
		if l, ok := labels[ev.Action]; ok && len(ev.Date) >= 10 {
			found("%s: %s", l, ev.Date[:10])
		}
	}
	if len(rd.Status) > 0 {
		info("STATUS: %s", shorten(strings.Join(rd.Status, ", "), 90))
	}
}

var (
	titleRe = regexp.MustCompile(`(?is)<title[^>]*>(.*?)</title>`)
	genRe   = regexp.MustCompile(`(?is)<meta[^>]+name=["']generator["'][^>]+content=["']([^"']+)`)
)

func httpCheck(d string) {
	var resp *http.Response
	var body []byte
	var err error
	base := "https://" + d
	resp, body, err = get(client, base+"/")
	if err != nil {
		warn("HTTPS NICHT ERREICHBAR: %s", shorten(err.Error(), 50))
		base = "http://" + d
		resp, body, err = get(client, base+"/")
		if err != nil {
			warn("HTTP NICHT ERREICHBAR")
			return
		}
	}
	found("STATUS: %d  %s", resp.StatusCode, shorten(resp.Request.URL.String(), 60))
	if s := resp.Header.Get("Server"); s != "" {
		info("SERVER: %s", shorten(s, 60))
	}
	if s := resp.Header.Get("X-Powered-By"); s != "" {
		info("POWERED-BY: %s", shorten(s, 60))
	}
	if m := titleRe.FindSubmatch(body); m != nil {
		info("TITEL: %s", shorten(string(m[1]), 70))
	}
	if m := genRe.FindSubmatch(body); m != nil {
		info("GENERATOR: %s", shorten(string(m[1]), 60))
	}
	checks := []struct{ h, label string }{
		{"Strict-Transport-Security", "HSTS"},
		{"Content-Security-Policy", "CSP"},
		{"X-Frame-Options", "X-FRAME-OPTIONS"},
		{"X-Content-Type-Options", "X-CONTENT-TYPE"},
		{"Referrer-Policy", "REFERRER-POLICY"},
		{"Permissions-Policy", "PERMISSIONS-POLICY"},
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
		found("SICHERHEITS-HEADER: %s", strings.Join(have, ", "))
	}
	if len(lack) > 0 {
		miss("HEADER FEHLEN: %s", strings.Join(lack, ", "))
	}
	for _, p := range []string{"/robots.txt", "/.well-known/security.txt"} {
		r2, b2, err := get(client, base+p)
		if err != nil {
			continue
		}
		t := strings.TrimSpace(string(b2))
		if r2.StatusCode == 200 && t != "" && !strings.HasPrefix(strings.ToLower(t), "<") {
			found("%s VORHANDEN", strings.ToUpper(p))
		} else {
			miss("%s FEHLT", strings.ToUpper(p))
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
			warn("KEIN TLS AUF PORT 443")
			return
		}
	}
	defer conn.Close()
	st := conn.ConnectionState()
	vers := map[uint16]string{tls.VersionTLS10: "TLS 1.0", tls.VersionTLS11: "TLS 1.1", tls.VersionTLS12: "TLS 1.2", tls.VersionTLS13: "TLS 1.3"}
	if verified {
		found("ZERTIFIKAT GUELTIG UND VERTRAUENSWUERDIG")
	} else {
		warn("ZERTIFIKAT NICHT VERTRAUENSWUERDIG")
	}
	info("PROTOKOLL: %s  %s", vers[st.Version], tls.CipherSuiteName(st.CipherSuite))
	if len(st.PeerCertificates) == 0 {
		return
	}
	c := st.PeerCertificates[0]
	info("AUSSTELLER: %s", shorten(c.Issuer.CommonName+" "+strings.Join(c.Issuer.Organization, " "), 70))
	info("GUELTIG: %s BIS %s", c.NotBefore.Format("2006-01-02"), c.NotAfter.Format("2006-01-02"))
	left := int(time.Until(c.NotAfter).Hours() / 24)
	if left < 0 {
		warn("ZERTIFIKAT ABGELAUFEN (VOR %d TAGEN)", -left)
	} else if left < 21 {
		warn("LAEUFT IN %d TAGEN AB", left)
	} else {
		found("NOCH %d TAGE GUELTIG", left)
	}
	names := c.DNSNames
	if len(names) > 0 {
		if len(names) > 8 {
			names = names[:8]
		}
		info("NAMEN: %s", strings.Join(names, ", "))
	}
}

func subdomains(d string) {
	crt := &http.Client{Timeout: 25 * time.Second}
	resp, body, err := get(crt, "https://crt.sh/?q=%25."+d+"&output=json")
	if err != nil || resp.StatusCode != 200 {
		warn("CRT.SH NICHT ERREICHBAR")
		return
	}
	var rows []struct {
		Name string `json:"name_value"`
	}
	if err := json.Unmarshal(body, &rows); err != nil {
		warn("CRT.SH-ANTWORT NICHT LESBAR (EVTL. ZU GROSS)")
		return
	}
	set := map[string]bool{}
	for _, r := range rows {
		for _, n := range strings.Split(r.Name, "\n") {
			n = strings.ToLower(strings.TrimPrefix(strings.TrimSpace(n), "*."))
			if n == d || strings.HasSuffix(n, "."+d) {
				set[n] = true
			}
		}
	}
	delete(set, d)
	if len(set) == 0 {
		miss("KEINE SUBDOMAINS IN ZERTIFIKATS-LOGS")
		return
	}
	names := make([]string, 0, len(set))
	for n := range set {
		names = append(names, n)
	}
	sort.Strings(names)
	info("%d SUBDOMAINS IN LOGS", len(names))
	limit := 60
	if len(names) < limit {
		limit = len(names)
	}
	type res struct {
		name string
		ips  []string
	}
	out := make([]res, limit)
	sem := make(chan struct{}, 10)
	var wg sync.WaitGroup
	for i := 0; i < limit; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			out[i] = res{names[i], ipsOf(names[i])}
		}(i)
	}
	wg.Wait()
	live, shown := 0, 0
	for _, r := range out {
		if len(r.ips) > 0 {
			live++
			if shown < 40 {
				found("%s  %s", r.name, r.ips[0])
				shown++
			}
		}
	}
	info("%d VON %d GEPRUEFTEN LOESEN AUF", live, limit)
	if len(names) > limit {
		info("%d WEITERE NICHT GEPRUEFT", len(names)-limit)
	}
}
