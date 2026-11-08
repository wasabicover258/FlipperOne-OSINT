package main

import (
	"encoding/json"
	"net"
	"strings"
)

func runIP(raw string) {
	ip := net.ParseIP(strings.TrimSpace(raw))
	head("IP check: %s", raw)
	if ip == nil {
		warn("Not a valid IP address")
		return
	}
	if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() {
		info("Private/local address: no public data")
		return
	}
	found("Public address (%s)", map[bool]string{true: "IPv4", false: "IPv6"}[ip.To4() != nil])

	ctx, cancel := dnsCtx(6)
	names, err := net.DefaultResolver.LookupAddr(ctx, ip.String())
	cancel()
	if err == nil && len(names) > 0 {
		found("rDNS: %s", strings.TrimSuffix(names[0], "."))
	} else {
		miss("No rDNS record")
	}

	head("Network")
	if resp, body, err := get(client, "https://ipinfo.io/"+ip.String()+"/json"); err != nil || resp.StatusCode != 200 {
		warn("ipinfo not reachable")
	} else {
		var d struct {
			Org      string `json:"org"`
			Country  string `json:"country"`
			Timezone string `json:"timezone"`
		}
		if json.Unmarshal(body, &d) == nil {
			if d.Org != "" {
				found("Operator (ASN): %s", shorten(d.Org, 70))
			}
			if d.Country != "" {
				found("Country: %s", d.Country)
			}
			if d.Timezone != "" {
				info("Timezone: %s", d.Timezone)
			}
		}
	}

	head("Open services (Shodan InternetDB)")
	resp, body, err := get(client, "https://internetdb.shodan.io/"+ip.String())
	if err != nil {
		warn("InternetDB not reachable")
		return
	}
	if resp.StatusCode == 404 {
		miss("No data for this address")
		return
	}
	var db struct {
		Ports     []int    `json:"ports"`
		Hostnames []string `json:"hostnames"`
		Tags      []string `json:"tags"`
		Vulns     []string `json:"vulns"`
	}
	if resp.StatusCode != 200 || json.Unmarshal(body, &db) != nil {
		warn("InternetDB: HTTP %d", resp.StatusCode)
		return
	}
	if len(db.Ports) > 0 {
		var ps []string
		for _, p := range db.Ports {
			ps = append(ps, itoa(p))
		}
		found("Ports: %s", strings.Join(ps, ", "))
	} else {
		miss("No open ports known")
	}
	if len(db.Hostnames) > 0 {
		info("Hostnames: %s", shorten(strings.Join(db.Hostnames, ", "), 90))
	}
	if len(db.Tags) > 0 {
		info("Tags: %s", strings.Join(db.Tags, ", "))
	}
	if len(db.Vulns) > 0 {
		v := db.Vulns
		if len(v) > 8 {
			v = v[:8]
		}
		warn("Known vulnerabilities (%d): %s", len(db.Vulns), strings.Join(v, ", "))
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	s := ""
	for n > 0 {
		s = string(rune('0'+n%10)) + s
		n /= 10
	}
	return s
}
