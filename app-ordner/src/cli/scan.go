package main

import (
	"bufio"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Native TCP port scanner (connect scan, like `nmap -sT`) with lightweight
// banner / version detection (`nmap -sV`). No external binary: every probe is
// a plain Go TCP or TLS connection, so it runs on the Flipper itself.
// ---------------------------------------------------------------------------

// Focused list for the infrastructure tree (many hosts, keep it quick).
var topPortsLite = []int{
	21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 587, 993, 995, 1433, 3306,
	3389, 5432, 6379, 8000, 8080, 8443, 8888, 9200, 27017,
}

// Wider list for the single-IP module, where the user asked about one host.
var topPortsFull = []int{
	21, 22, 23, 25, 53, 80, 81, 88, 110, 111, 135, 139, 143, 161, 389, 443,
	445, 465, 514, 587, 631, 636, 993, 995, 1025, 1080, 1194, 1433, 1521,
	1723, 2049, 2082, 2083, 2086, 2087, 2095, 2096, 2181, 2222, 2375, 2376,
	3000, 3128, 3306, 3389, 3690, 4444, 5000, 5060, 5432, 5601, 5672, 5900,
	5984, 5985, 6379, 6443, 7001, 8000, 8008, 8080, 8081, 8086, 8088, 8089,
	8443, 8500, 8888, 9000, 9042, 9092, 9200, 9300, 9418, 9999, 10000, 11211,
	15672, 27017, 50070,
}

// portScan returns the open TCP ports, sorted ascending.
func portScan(ip string, ports []int, timeout time.Duration, concurrency int) []int {
	var mu sync.Mutex
	var open []int
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	for _, p := range ports {
		wg.Add(1)
		go func(p int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			conn, err := net.DialTimeout("tcp", net.JoinHostPort(ip, itoa(p)), timeout)
			if err != nil {
				return
			}
			conn.Close()
			mu.Lock()
			open = append(open, p)
			mu.Unlock()
		}(p)
	}
	wg.Wait()
	sort.Ints(open)
	return open
}

var tlsPorts = map[int]bool{443: true, 465: true, 636: true, 993: true, 995: true,
	8443: true, 6443: true, 2083: true, 2087: true, 2096: true, 5601: true}

var httpPorts = map[int]bool{80: true, 81: true, 591: true, 2082: true, 2086: true,
	2095: true, 3000: true, 5000: true, 8000: true, 8008: true, 8080: true, 8081: true,
	8088: true, 8089: true, 8888: true, 9000: true, 9200: true, 10000: true, 15672: true}

// grabBanner names the service on an open port and reads a short version banner.
func grabBanner(ip string, port int) string {
	timeout := 2200 * time.Millisecond

	if tlsPorts[port] {
		d := &net.Dialer{Timeout: timeout}
		conn, err := tls.DialWithDialer(d, "tcp", net.JoinHostPort(ip, itoa(port)),
			&tls.Config{InsecureSkipVerify: true})
		if err == nil {
			defer conn.Close()
			st := conn.ConnectionState()
			cn := ""
			if len(st.PeerCertificates) > 0 {
				cn = st.PeerCertificates[0].Subject.CommonName
			}
			v := map[uint16]string{tls.VersionTLS10: "TLS1.0", tls.VersionTLS11: "TLS1.1",
				tls.VersionTLS12: "TLS1.2", tls.VersionTLS13: "TLS1.3"}[st.Version]
			return shorten(strings.TrimSpace(v+" "+cn), 46)
		}
		return ""
	}

	conn, err := net.DialTimeout("tcp", net.JoinHostPort(ip, itoa(port)), timeout)
	if err != nil {
		return ""
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(timeout))

	if httpPorts[port] {
		fmt.Fprintf(conn, "HEAD / HTTP/1.0\r\nHost: %s\r\nUser-Agent: osint\r\n\r\n", ip)
		r := bufio.NewReader(conn)
		var server, powered string
		for i := 0; i < 40; i++ {
			line, err := r.ReadString('\n')
			if err != nil {
				break
			}
			l := strings.TrimSpace(line)
			low := strings.ToLower(l)
			if strings.HasPrefix(low, "server:") {
				server = strings.TrimSpace(l[7:])
			} else if strings.HasPrefix(low, "x-powered-by:") {
				powered = strings.TrimSpace(l[13:])
			}
			if l == "" {
				break
			}
		}
		b := server
		if powered != "" {
			b = strings.TrimSpace(b + " / " + powered)
		}
		return shorten(b, 46)
	}

	// Services that greet first: SSH, FTP, SMTP, POP, IMAP, Redis, ...
	buf := make([]byte, 200)
	n, _ := conn.Read(buf)
	return sanitizeBanner(buf[:n])
}

func sanitizeBanner(b []byte) string {
	s := strings.TrimSpace(string(b))
	if i := strings.IndexAny(s, "\r\n"); i >= 0 {
		s = s[:i]
	}
	var out strings.Builder
	for _, r := range s {
		if r >= 32 && r < 127 {
			out.WriteRune(r)
		}
	}
	return shorten(out.String(), 46)
}

// bannerFor returns a short combined banner for the tree: the most telling of
// the host's open ports (ssh, http, https, mail), joined compactly.
func bannerFor(ip string, open []int) string {
	prefer := []int{22, 80, 443, 21, 25, 8080, 8443}
	var parts []string
	for _, p := range prefer {
		if len(parts) >= 2 {
			break
		}
		if !containsInt(open, p) {
			continue
		}
		if b := grabBanner(ip, p); b != "" {
			parts = append(parts, itoa(p)+" "+b)
		}
	}
	return shorten(strings.Join(parts, "; "), 70)
}

func containsInt(s []int, v int) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// Zone transfer (AXFR) attempt, like `dnsrecon -t axfr`: a nameserver that
// answers hands out the entire DNS zone. Done natively over raw TCP DNS, so it
// does not depend on any external API.
// ---------------------------------------------------------------------------

func zoneTransfer(d string) {
	ctx, cancel := dnsCtx(6)
	nss, err := net.DefaultResolver.LookupNS(ctx, d)
	cancel()
	if err != nil || len(nss) == 0 {
		info("No nameservers found for a zone-transfer test")
		return
	}
	tested, leaked := 0, false
	for _, ns := range nss {
		if tested >= 4 {
			break
		}
		host := strings.TrimSuffix(ns.Host, ".")
		ips := ipsOf(host)
		if len(ips) == 0 {
			continue
		}
		tested++
		if ok, records := tryAXFR(ips[0], d); ok {
			warn("AXFR ALLOWED on %s - full zone exposed (~%d records)", shorten(host, 34), records)
			leaked = true
		}
	}
	if tested == 0 {
		info("No nameserver reachable for a zone-transfer test")
	} else if !leaked {
		found("Zone transfer (AXFR): refused by all %d tested (good)", tested)
	}
}

func tryAXFR(nsIP, domain string) (bool, int) {
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(nsIP, "53"), 6*time.Second)
	if err != nil {
		return false, 0
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(8 * time.Second))

	q := buildDNSQuery(domain, 252) // 252 = AXFR
	msg := append([]byte{byte(len(q) >> 8), byte(len(q))}, q...)
	if _, err := conn.Write(msg); err != nil {
		return false, 0
	}
	var lenBuf [2]byte
	if _, err := readFull(conn, lenBuf[:]); err != nil {
		return false, 0
	}
	rlen := int(lenBuf[0])<<8 | int(lenBuf[1])
	if rlen < 12 || rlen > 65535 {
		return false, 0
	}
	resp := make([]byte, rlen)
	if _, err := readFull(conn, resp); err != nil {
		return false, 0
	}
	rcode := resp[3] & 0x0f
	ancount := int(resp[6])<<8 | int(resp[7])
	return rcode == 0 && ancount > 0, ancount
}

func readFull(conn net.Conn, b []byte) (int, error) {
	got := 0
	for got < len(b) {
		n, err := conn.Read(b[got:])
		if n > 0 {
			got += n
		}
		if err != nil {
			return got, err
		}
	}
	return got, nil
}

func buildDNSQuery(name string, qtype uint16) []byte {
	b := []byte{0x13, 0x37, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}
	for _, label := range strings.Split(strings.TrimSuffix(name, "."), ".") {
		if label == "" {
			continue
		}
		b = append(b, byte(len(label)))
		b = append(b, []byte(label)...)
	}
	b = append(b, 0x00)
	b = append(b, byte(qtype>>8), byte(qtype))
	b = append(b, 0x00, 0x01)
	return b
}

// ---------------------------------------------------------------------------
// Web exposure probe: a short, curated check for sensitive paths and risky
// configuration, in the spirit of dirb / Nikto but kept small so it stays
// light. It only reports what exists; it does not attack anything.
// ---------------------------------------------------------------------------

type exposure struct {
	path, label string
	secret      bool
}

var exposurePaths = []exposure{
	{"/.git/HEAD", ".git repository exposed", true},
	{"/.env", ".env file exposed", true},
	{"/.svn/entries", ".svn repository exposed", true},
	{"/.DS_Store", ".DS_Store exposed", true},
	{"/config.php.bak", "config backup exposed", true},
	{"/backup.zip", "backup archive exposed", true},
	{"/server-status", "Apache server-status exposed", true},
	{"/server-info", "Apache server-info exposed", true},
	{"/phpinfo.php", "phpinfo() exposed", true},
	{"/.htaccess", ".htaccess exposed", true},
	{"/.well-known/security.txt", "security.txt", false},
	{"/sitemap.xml", "sitemap.xml", false},
	{"/wp-login.php", "WordPress login", false},
	{"/admin/", "admin area", false},
}

func webExposure(d string) {
	base := "https://" + d
	if resp, _, err := get(client, base+"/"); err != nil || resp == nil {
		base = "http://" + d
	}
	var mu sync.Mutex
	secrets, infos := 0, 0
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup
	for _, e := range exposurePaths {
		wg.Add(1)
		go func(e exposure) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			resp, body, err := get(client, base+e.path)
			if err != nil || resp.StatusCode != 200 {
				return
			}
			t := strings.TrimSpace(string(body))
			if t == "" {
				return
			}
			// A site that serves its HTML app for every path is not a real hit
			// for a sensitive dotfile.
			if e.secret && strings.HasPrefix(strings.ToLower(t), "<!doctype") {
				return
			}
			mu.Lock()
			if e.secret {
				secrets++
				warn("%s", e.label)
			} else {
				infos++
				found("%s present", e.label)
			}
			mu.Unlock()
		}(e)
	}
	wg.Wait()

	if _, body, err := get(client, base+"/"); err == nil {
		if strings.Contains(strings.ToLower(string(body)), "index of /") {
			warn("Directory listing enabled on /")
			secrets++
		}
	}
	if m := riskyMethods(base); m != "" {
		warn("Risky HTTP methods allowed: %s", m)
	}
	if secrets == 0 && infos == 0 {
		info("No exposed paths from the quick check")
	} else if secrets == 0 {
		info("No sensitive files exposed")
	}
}

func riskyMethods(base string) string {
	req, err := http.NewRequest("OPTIONS", base+"/", nil)
	if err != nil {
		return ""
	}
	req.Header.Set("User-Agent", userAgent)
	resp, err := client.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	allow := strings.ToUpper(resp.Header.Get("Allow"))
	var risky []string
	for _, m := range []string{"PUT", "DELETE", "TRACE", "CONNECT", "PATCH"} {
		if strings.Contains(allow, m) {
			risky = append(risky, m)
		}
	}
	return strings.Join(risky, ", ")
}
