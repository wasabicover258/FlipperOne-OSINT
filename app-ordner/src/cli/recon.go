package main

import (
	"encoding/json"
	"fmt"
	"net"
	"sort"
	"strings"
	"sync"
)

// ---------------------------------------------------------------------------
// DNS over HTTPS
//
// Go's standard resolver only speaks A/AAAA/MX/NS/TXT/CNAME/SRV/PTR. For the
// record types that matter for a security review (CAA, SOA, DNSKEY/DS for
// DNSSEC, TLSA) we query DNS over HTTPS. It is also more reliable than the
// system resolver inside the emulator, which has no real DNS of its own.
// ---------------------------------------------------------------------------

type dohAnswer struct {
	Name string `json:"name"`
	Type int    `json:"type"`
	TTL  int    `json:"TTL"`
	Data string `json:"data"`
}

type dohReply struct {
	Status int         `json:"Status"`
	AD     bool        `json:"AD"` // authenticated data = DNSSEC-validated
	Answer []dohAnswer `json:"Answer"`
}

var dohEndpoints = []string{
	"https://dns.google/resolve?",
	"https://cloudflare-dns.com/dns-query?",
}

// doh resolves name/rrtype over HTTPS. rrtype is a name like "CAA" or "SOA".
func doh(name, rrtype string) (*dohReply, error) {
	var lastErr error
	for _, ep := range dohEndpoints {
		url := ep + "name=" + name + "&type=" + rrtype
		resp, body, err := get(client, url)
		if err != nil {
			lastErr = err
			continue
		}
		if resp.StatusCode != 200 {
			lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
			continue
		}
		var rep dohReply
		if err := json.Unmarshal(body, &rep); err != nil {
			lastErr = err
			continue
		}
		return &rep, nil
	}
	return nil, lastErr
}

// dohData returns the data strings of all answers matching the requested type.
func dohData(name, rrtype string) []string {
	rep, err := doh(name, rrtype)
	if err != nil || rep == nil {
		return nil
	}
	want := dnsTypeNum[rrtype]
	var out []string
	for _, a := range rep.Answer {
		if want == 0 || a.Type == want {
			out = append(out, strings.Trim(a.Data, "\""))
		}
	}
	return out
}

var dnsTypeNum = map[string]int{
	"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12, "MX": 15, "TXT": 16,
	"AAAA": 28, "SRV": 33, "DS": 43, "DNSKEY": 48, "TLSA": 52, "CAA": 257, "HTTPS": 65,
}

// ---------------------------------------------------------------------------
// IP enrichment, shared by the IP module and the domain infrastructure tree.
// ---------------------------------------------------------------------------

type ipData struct {
	ip      string
	rdns    string
	asn     string // e.g. "AS15169"
	org     string
	country string
	city    string
	region  string
	ports   []int
	cpes    []string
	tags    []string
	vulns   []string
	ok      bool // at least one source answered
}

var (
	ipCache   = map[string]*ipData{}
	ipCacheMu sync.Mutex
)

// enrichIP gathers rDNS + ipinfo + Shodan InternetDB for one address. Results
// are cached for the lifetime of the process so the tree does not query the
// same address twice.
func enrichIP(ip string) *ipData {
	ipCacheMu.Lock()
	if d, ok := ipCache[ip]; ok {
		ipCacheMu.Unlock()
		return d
	}
	ipCacheMu.Unlock()

	d := &ipData{ip: ip}
	var wg sync.WaitGroup
	wg.Add(3)

	go func() {
		defer wg.Done()
		ctx, cancel := dnsCtx(4)
		names, err := net.DefaultResolver.LookupAddr(ctx, ip)
		cancel()
		if err == nil && len(names) > 0 {
			d.rdns = strings.TrimSuffix(names[0], ".")
		}
	}()

	go func() {
		defer wg.Done()
		resp, body, err := get(client, "https://ipinfo.io/"+ip+"/json")
		if err != nil || resp.StatusCode != 200 {
			return
		}
		var r struct {
			Org, Country, City, Region, Hostname string
		}
		if json.Unmarshal(body, &r) == nil {
			d.org = r.Org
			d.country = r.Country
			d.city = r.City
			d.region = r.Region
			// ipinfo prefixes the org with the ASN, e.g. "AS15169 Google LLC".
			if strings.HasPrefix(r.Org, "AS") {
				if sp := strings.IndexByte(r.Org, ' '); sp > 0 {
					d.asn = r.Org[:sp]
					d.org = strings.TrimSpace(r.Org[sp+1:])
				}
			}
			if d.rdns == "" && r.Hostname != "" {
				d.rdns = r.Hostname
			}
			d.ok = true
		}
	}()

	go func() {
		defer wg.Done()
		resp, body, err := get(client, "https://internetdb.shodan.io/"+ip)
		if err != nil || resp.StatusCode != 200 {
			return
		}
		var r struct {
			Ports     []int    `json:"ports"`
			Cpes      []string `json:"cpes"`
			Hostnames []string `json:"hostnames"`
			Tags      []string `json:"tags"`
			Vulns     []string `json:"vulns"`
		}
		if json.Unmarshal(body, &r) == nil {
			d.ports = r.Ports
			d.cpes = r.Cpes
			d.tags = r.Tags
			d.vulns = r.Vulns
			d.ok = true
		}
	}()

	wg.Wait()
	sort.Ints(d.ports)

	ipCacheMu.Lock()
	ipCache[ip] = d
	ipCacheMu.Unlock()
	return d
}

// portsStr renders a port list compactly.
func portsStr(ports []int) string {
	if len(ports) == 0 {
		return ""
	}
	var s []string
	for _, p := range ports {
		s = append(s, itoa(p))
	}
	return strings.Join(s, ", ")
}

// wellKnownPort maps a port to a short service label where it is unambiguous.
var wellKnownPort = map[int]string{
	21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http",
	110: "pop3", 143: "imap", 443: "https", 465: "smtps", 587: "submission",
	993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle", 2082: "cpanel",
	2083: "cpanel", 2222: "ssh-alt", 3000: "dev-http", 3306: "mysql",
	3389: "rdp", 5432: "postgres", 5900: "vnc", 5985: "winrm", 6379: "redis",
	8000: "http-alt", 8080: "http-proxy", 8443: "https-alt", 8888: "http-alt",
	9200: "elasticsearch", 11211: "memcached", 27017: "mongodb",
}

// ---------------------------------------------------------------------------
// RDAP for IP addresses: the netblock, its operator and the abuse contact of
// the network (the operator's role mailbox, not a person).
// ---------------------------------------------------------------------------

func rdapIP(ip string) {
	resp, body, err := get(client, "https://rdap.org/ip/"+ip)
	if err != nil || resp.StatusCode != 200 {
		return
	}
	var r struct {
		Handle       string `json:"handle"`
		StartAddress string `json:"startAddress"`
		EndAddress   string `json:"endAddress"`
		Name         string `json:"name"`
		Type         string `json:"type"`
		Country      string `json:"country"`
		Entities     []struct {
			Roles      []string `json:"roles"`
			VcardArray []any    `json:"vcardArray"`
		} `json:"entities"`
	}
	if json.Unmarshal(body, &r) != nil {
		return
	}
	if r.StartAddress != "" && r.EndAddress != "" {
		found("Netblock: %s - %s", r.StartAddress, r.EndAddress)
	}
	if r.Name != "" {
		found("Network name: %s", shorten(r.Name, 60))
	}
	if r.Type != "" {
		info("Allocation: %s", r.Type)
	}
	abuse := rdapAbuse(r.Entities)
	if abuse != "" {
		info("Abuse contact: %s", abuse)
	}
}

// rdapAbuse digs the abuse role mailbox out of nested RDAP entities.
func rdapAbuse(entities []struct {
	Roles      []string `json:"roles"`
	VcardArray []any    `json:"vcardArray"`
}) string {
	for _, e := range entities {
		isAbuse := false
		for _, role := range e.Roles {
			if role == "abuse" {
				isAbuse = true
			}
		}
		if !isAbuse || len(e.VcardArray) < 2 {
			continue
		}
		props, _ := e.VcardArray[1].([]any)
		for _, p := range props {
			arr, _ := p.([]any)
			if len(arr) >= 4 && arr[0] == "email" {
				if s, ok := arr[3].(string); ok {
					return s
				}
			}
		}
	}
	return ""
}

// ---------------------------------------------------------------------------
// A curated list of common subdomain labels for a light DNS sweep, to catch
// hosts that never appeared in a certificate log.
// ---------------------------------------------------------------------------

var commonSubs = []string{
	"www", "mail", "webmail", "smtp", "imap", "pop", "mx", "mx1", "mx2",
	"ns1", "ns2", "ns3", "dns", "autodiscover", "autoconfig", "cpanel", "whm",
	"webdisk", "mobile", "m", "api", "api2", "apiv1", "dev", "dev2", "staging",
	"stage", "test", "testing", "qa", "uat", "sandbox", "demo", "beta", "preview",
	"prod", "production", "admin", "administrator", "portal", "dashboard", "panel",
	"login", "signin", "sso", "auth", "accounts", "secure", "vpn", "remote",
	"gateway", "gw", "fw", "firewall", "proxy", "cache", "cdn", "static", "assets",
	"img", "images", "media", "files", "download", "downloads", "upload", "docs",
	"doc", "wiki", "blog", "news", "shop", "store", "cart", "checkout", "pay",
	"payment", "billing", "git", "gitlab", "github", "svn", "jenkins", "ci", "cd",
	"build", "registry", "nexus", "artifactory", "sonar", "grafana", "kibana",
	"prometheus", "status", "health", "monitor", "monitoring", "nagios", "zabbix",
	"splunk", "elk", "log", "logs", "metrics", "jira", "confluence", "support",
	"help", "helpdesk", "ticket", "crm", "erp", "intranet", "extranet", "internal",
	"corp", "ad", "ldap", "radius", "db", "database", "mysql", "postgres", "mongo",
	"redis", "backup", "backups", "old", "new", "legacy", "app", "apps", "web",
	"web1", "web2", "server", "host", "cloud", "s3", "storage", "ftp", "sftp",
	"ssh", "owa", "exchange", "lync", "sip", "voip", "chat", "forum", "community",
	"video", "stream", "live", "ns", "email", "mailserver", "relay", "edge",
}

// ---------------------------------------------------------------------------
// Additional passive subdomain / host sources (theHarvester / recon-ng style),
// all free and keyless. Each is best-effort: a source that is down or rate-
// limited simply contributes nothing.
// ---------------------------------------------------------------------------

// certspotterSubs pulls names from the certspotter certificate-transparency API.
func certspotterSubs(d string) []string {
	url := "https://api.certspotter.com/v1/issuances?domain=" + d +
		"&include_subdomains=true&expand=dns_names"
	resp, body, err := get(client, url)
	if err != nil || resp.StatusCode != 200 {
		return nil
	}
	var rows []struct {
		DNSNames []string `json:"dns_names"`
	}
	if json.Unmarshal(body, &rows) != nil {
		return nil
	}
	var out []string
	for _, r := range rows {
		out = append(out, r.DNSNames...)
	}
	return out
}

// hackertargetSubs uses HackerTarget's hostsearch (host,ip per line); it gives
// the resolving IP directly, which seeds the infrastructure tree.
func hackertargetSubs(d string) map[string][]string {
	resp, body, err := get(client, "https://api.hackertarget.com/hostsearch/?q="+d)
	if err != nil || resp.StatusCode != 200 {
		return nil
	}
	out := map[string][]string{}
	for _, line := range strings.Split(string(body), "\n") {
		parts := strings.SplitN(strings.TrimSpace(line), ",", 2)
		if len(parts) != 2 {
			continue
		}
		host := strings.ToLower(strings.TrimSpace(parts[0]))
		ip := strings.TrimSpace(parts[1])
		if host != "" && net.ParseIP(ip) != nil {
			out[host] = append(out[host], ip)
		}
	}
	return out
}

// zoneTransfer reports whether the domain's nameservers leak the full zone via
// AXFR (a serious misconfiguration). It uses HackerTarget's zonetransfer probe.
func zoneTransfer(d string) {
	resp, body, err := get(client, "https://api.hackertarget.com/zonetransfer/?q="+d)
	if err != nil || resp.StatusCode != 200 {
		return
	}
	t := strings.TrimSpace(string(body))
	low := strings.ToLower(t)
	switch {
	case t == "" || strings.Contains(low, "error") || strings.Contains(low, "failed") ||
		strings.Contains(low, "does not allow") || strings.Contains(low, "refused") ||
		strings.Contains(low, "timed out") || strings.Contains(low, "no ns"):
		found("Zone transfer (AXFR): refused (good)")
	case strings.Contains(low, "api count") || strings.Contains(low, "api limit"):
		// Source rate-limited; say nothing rather than imply a result.
	default:
		lines := 0
		for _, l := range strings.Split(t, "\n") {
			if strings.TrimSpace(l) != "" {
				lines++
			}
		}
		warn("Zone transfer (AXFR) ALLOWED - full DNS zone exposed (%d records)", lines)
	}
}
