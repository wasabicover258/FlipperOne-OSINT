package main

import (
	"net"
	"strings"
	"time"
)

func runIP(raw string) {
	ip := net.ParseIP(strings.TrimSpace(raw))
	head("IP recon: %s", raw)
	if ip == nil {
		warn("Not a valid IP address")
		return
	}
	if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() {
		info("Private/local address: no public data")
		return
	}
	kind := "IPv6"
	if ip.To4() != nil {
		kind = "IPv4"
	}
	found("Public address (%s)", kind)

	d := enrichIP(ip.String())

	head("Reverse DNS")
	if d.rdns != "" {
		found("rDNS: %s", d.rdns)
	} else {
		miss("No rDNS record")
	}

	head("Network")
	if d.asn != "" {
		found("ASN: %s", d.asn)
	}
	if d.org != "" {
		found("Operator: %s", shorten(d.org, 70))
	}
	loc := strings.TrimSpace(strings.Join(filterEmpty(d.city, d.region, d.country), ", "))
	if loc != "" {
		found("Location: %s", loc)
	}
	if !d.ok && d.rdns == "" {
		warn("No public network data available")
	}

	head("Registration (RDAP)")
	rdapIP(ip.String())

	head("Open services (Shodan InternetDB)")
	if len(d.ports) > 0 {
		found("Ports: %s", portsStr(d.ports))
		// Name the well-known ones so the reader sees the exposed services.
		var svc []string
		for _, p := range d.ports {
			if name, ok := wellKnownPort[p]; ok {
				svc = append(svc, itoa(p)+"/"+name)
			}
		}
		if len(svc) > 0 {
			info("Services: %s", shorten(strings.Join(svc, ", "), 90))
		}
	} else {
		miss("No open ports known")
	}
	if len(d.cpes) > 0 {
		c := d.cpes
		if len(c) > 6 {
			c = c[:6]
		}
		info("Software (CPE): %s", shorten(strings.Join(c, ", "), 90))
	}
	if len(d.tags) > 0 {
		info("Tags: %s", strings.Join(d.tags, ", "))
	}
	if len(d.vulns) > 0 {
		v := d.vulns
		if len(v) > 10 {
			v = v[:10]
		}
		warn("Known vulnerabilities (%d): %s", len(d.vulns), strings.Join(v, ", "))
	} else if d.ok {
		info("No known CVEs for this address")
	}

	// Live connect scan of the address itself (nmap-style), plus banners.
	head("Live port scan")
	open := portScan(ip.String(), topPortsFull, 1400*time.Millisecond, 80)
	if len(open) == 0 {
		miss("No open TCP ports found (of %d probed)", len(topPortsFull))
		return
	}
	found("Open now: %s", shorten(portsStr(open), 90))
	var svc []string
	for _, p := range open {
		if name, ok := wellKnownPort[p]; ok {
			svc = append(svc, itoa(p)+"/"+name)
		}
	}
	if len(svc) > 0 {
		info("Services: %s", shorten(strings.Join(svc, ", "), 90))
	}
	// Banner-grab the first few open ports for version hints.
	shown := 0
	for _, p := range open {
		if shown >= 5 {
			break
		}
		if b := grabBanner(ip.String(), p); b != "" {
			info("%d: %s", p, b)
			shown++
		}
	}
}

func filterEmpty(ss ...string) []string {
	var out []string
	for _, s := range ss {
		if s != "" {
			out = append(out, s)
		}
	}
	return out
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	s := ""
	for n > 0 {
		s = string(rune('0'+n%10)) + s
		n /= 10
	}
	if neg {
		s = "-" + s
	}
	return s
}
