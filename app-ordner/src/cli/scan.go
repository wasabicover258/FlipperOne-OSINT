package main

import (
	"crypto/tls"
	"net"
	"sort"
	"strings"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Active TCP port scan (connect scan, like nmap -sT) plus a light banner grab
// for service-version hints (like nmap -sV). This probes the target host's own
// ports only; it is the infrastructure equivalent of nmap, not an attack.
// ---------------------------------------------------------------------------

// A broad list for a single IP target (IP module).
var topPortsFull = []int{
	21, 22, 23, 25, 26, 53, 69, 80, 81, 88, 110, 111, 113, 119, 123, 135, 137,
	139, 143, 161, 179, 199, 389, 427, 443, 444, 445, 465, 500, 512, 513, 514,
	515, 543, 544, 548, 554, 587, 631, 636, 646, 873, 990, 993, 995, 1025, 1026,
	1080, 1194, 1433, 1521, 1723, 1883, 2049, 2082, 2083, 2086, 2087, 2095, 2096,
	2181, 2222, 2375, 2376, 2483, 3000, 3306, 3389, 3690, 4000, 4040, 4443, 4444,
	4567, 4848, 5000, 5060, 5222, 5432, 5601, 5672, 5900, 5985, 5986, 6000, 6379,
	6443, 6667, 7000, 7001, 7070, 7443, 8000, 8008, 8080, 8081, 8083, 8085, 8088,
	8090, 8161, 8243, 8333, 8443, 8500, 8530, 8531, 8686, 8888, 8983, 9000, 9042,
	9090, 9092, 9100, 9200, 9300, 9418, 9443, 9999, 10000, 11211, 15672, 27017,
	27018, 28017, 50000,
}

// A focused list for the tree, where many IPs are scanned (keeps it fast).
var topPortsLite = []int{
	21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 465, 587, 993,
	995, 1433, 1521, 2082, 2083, 3000, 3306, 3389, 5432, 5900, 6379, 8000, 8080,
	8443, 8888, 9200, 11211, 27017,
}

// portScan returns the open TCP ports from the list, within a time budget.
func portScan(ip string, ports []int, timeout time.Duration, conc int) []int {
	var mu sync.Mutex
	var open []int
	sem := make(chan struct{}, conc)
	var wg sync.WaitGroup
	for _, p := range ports {
		wg.Add(1)
		go func(p int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			c, err := net.DialTimeout("tcp", net.JoinHostPort(ip, itoa(p)), timeout)
			if err != nil {
				return
			}
			c.Close()
			mu.Lock()
			open = append(open, p)
			mu.Unlock()
		}(p)
	}
	wg.Wait()
	sort.Ints(open)
	return open
}

// grabBanner reads a short service banner from one open port. For HTTP it asks
// for the headers; for ports that greet first (SSH, SMTP, FTP) it just reads.
func grabBanner(ip string, port int) string {
	addr := net.JoinHostPort(ip, itoa(port))
	d := net.Dialer{Timeout: 3 * time.Second}

	// TLS ports: read the certificate's common name as the "banner".
	if port == 443 || port == 8443 || port == 993 || port == 995 || port == 465 || port == 4443 || port == 9443 {
		conn, err := tls.DialWithDialer(&d, "tcp", addr, &tls.Config{InsecureSkipVerify: true})
		if err != nil {
			return ""
		}
		defer conn.Close()
		st := conn.ConnectionState()
		if len(st.PeerCertificates) > 0 {
			return "TLS " + shorten(st.PeerCertificates[0].Subject.CommonName, 40)
		}
		return "TLS"
	}

	conn, err := d.Dial("tcp", addr)
	if err != nil {
		return ""
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(3 * time.Second))

	httpPort := port == 80 || port == 8080 || port == 8000 || port == 8008 ||
		port == 8081 || port == 8888 || port == 3000 || port == 5000 || port == 9000
	if httpPort {
		conn.Write([]byte("HEAD / HTTP/1.0\r\nHost: " + ip + "\r\nUser-Agent: " + userAgent + "\r\n\r\n"))
	}
	buf := make([]byte, 1024)
	n, _ := conn.Read(buf)
	if n <= 0 {
		return ""
	}
	text := string(buf[:n])
	if httpPort {
		for _, line := range strings.Split(text, "\n") {
			l := strings.ToLower(strings.TrimSpace(line))
			if strings.HasPrefix(l, "server:") {
				return "HTTP " + shorten(strings.TrimSpace(line[len("server:"):]), 40)
			}
		}
		// No Server header: report the status line.
		if i := strings.IndexByte(text, '\r'); i > 0 {
			return shorten(text[:i], 40)
		}
	}
	// First line of whatever the service greeted with.
	line := text
	if i := strings.IndexAny(line, "\r\n"); i > 0 {
		line = line[:i]
	}
	line = strings.TrimSpace(ascii(line))
	if len(line) < 2 {
		return ""
	}
	return shorten(line, 44)
}

// bannerFor picks a representative port to banner-grab from an open set, so the
// tree shows one useful service string per host without probing every port.
func bannerFor(ip string, open []int) string {
	pref := []int{443, 80, 8080, 8443, 22, 25, 21, 3389, 3306, 5432, 6379}
	for _, p := range pref {
		for _, o := range open {
			if o == p {
				if b := grabBanner(ip, p); b != "" {
					return itoa(p) + " " + b
				}
			}
		}
	}
	// Fall back to the first open port.
	if len(open) > 0 {
		if b := grabBanner(ip, open[0]); b != "" {
			return itoa(open[0]) + " " + b
		}
	}
	return ""
}
